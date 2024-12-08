from datetime import datetime
from urllib.parse import quote
import requests
import logging
import os
import json  # For JSON formatting in logs
import re    # For phone number sanitization

# Set up logging to write to 'console.log' in the same folder as the script
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(script_dir, 'console.log')
logging.basicConfig(
    filename=log_file,
    filemode='w',  # Overwrite the log file each time the script runs
    level=logging.INFO,
    format='%(message)s'  # We'll handle JSON formatting ourselves
)

# Helper function to log messages in JSON format
def log_json(level, message, data=None):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message
    }
    if data is not None:
        log_entry["data"] = data
    json_log = json.dumps(log_entry, ensure_ascii=False)
    if level == "INFO":
        logging.info(json_log)
    elif level == "ERROR":
        logging.error(json_log)
    else:
        logging.debug(json_log)

# Load configurations from config.txt
def load_config(file_path='config.txt'):
    config = {}
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config

# Fetch environment variables from config
config = load_config()
PRIORITY_API_URL = config.get('PRIORITY_API_URL')
PRIORITY_API_USER = config.get('PRIORITY_API_USER')
PRIORITY_API_PASSWORD = config.get('PRIORITY_API_PASSWORD')
ATERA_API_KEY = config.get('ATERA_API_KEY')

# Sync flags
# Convert to bool from string
SYNC_CUSTOMERS = bool(int(config.get('SYNC_CUSTOMERS', 0)))
SYNC_CONTACTS = bool(int(config.get('SYNC_CONTACTS', 0)))
SYNC_CONTRACTS = bool(int(config.get('SYNC_CONTRACTS', 0)))
SYNC_SERVICE_CALLS = bool(int(config.get('SYNC_SERVICE_CALLS', 0)))

# ------------------- PHONE NUMBER SANITIZATION -------------------
def sanitize_phone_number(phone_number):
    """Sanitize phone numbers to include only '+', '-', and digits."""
    if not phone_number:
        return None
    # Keep only '+', '-', and digits
    sanitized = re.sub(r'[^+\-\d]', '', phone_number)
    # Check if there are any digits left
    if re.search(r'\d', sanitized):
        return sanitized
    else:
        return None

# ------------------- SYNC CUSTOMERS -------------------
def get_priority_customers():
    """Fetch customers from Priority with specific fields."""
    select_fields = 'CUSTNAME,CUSTDES,HOSTNAME,WTAXNUM,PHONE,FAX,ADDRESS,STATEA,STATENAME,STATE,ZIP'
    url = f"{PRIORITY_API_URL}/CUSTOMERS?$select={select_fields}"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching Priority customers: {response.status_code}", {"response": response.text})
    response.raise_for_status()
    return response.json()['value']

def get_atera_customers():
    """Fetch all existing customers from Atera and their 'Priority Customer Number' custom field."""
    url = "https://app.atera.com/api/v3/customers"
    headers = {
        'X-Api-Key': ATERA_API_KEY
    }
    customers = []
    page = 1
    items_in_page = 50  # Max items per page is 50

    while True:
        log_json("INFO", f"Fetching customers from Atera, page {page}...")
        params = {'page': page, 'itemsInPage': items_in_page}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log_json("ERROR", f"Error fetching Atera customers: {response.status_code}", {"response": response.text})
            response.raise_for_status()
        data = response.json()
        items = data.get('items', [])
        if not items:
            break
        customers.extend(items)
        page += 1

    # Now fetch the 'Priority Customer Number' custom field for each customer
    for i, customer in enumerate(customers):
        if (i + 1) % 100 == 0 or i == 0:
            log_json("INFO", f"Fetching custom fields for customers {i + 1}/{len(customers)}...")
        customer_id = customer['CustomerID']
        custom_field_name = 'Priority Customer Number'
        custom_field_value = get_atera_custom_field(customer_id, custom_field_name)
        customer['PriorityCustomerNumber'] = custom_field_value

    return customers

def get_atera_custom_field(customer_id, field_name):
    """Fetch the value of a custom field for a specific customer."""
    url = f"https://app.atera.com/api/v3/customvalues/customerfield/{customer_id}/{field_name}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'text/html'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()[0]['ValueAsString']
    elif response.status_code == 404:
        # Field not found for this customer
        return None
    else:
        log_json("ERROR", f"Error fetching custom field '{field_name}' for customer ID {customer_id}", {"status_code": response.status_code, "response": response.text})
        return None

def create_atera_customer(customer):
    """Create a customer in Atera, and then update the 'Priority Customer Number' custom field."""
    url = "https://app.atera.com/api/v3/customers"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json'
    }
    data = {
        "CustomerName": customer['CUSTDES'],
        "CreatedOn": datetime.utcnow().isoformat() + "Z",
        "BusinessNumber": customer.get('BUSINESSNUMBER', ''),
        "Domain": customer.get('DOMAIN', ''),
        "Address": customer.get('ADDRESS', ''),
        "City": customer.get('CITY', ''),
        "State": customer.get('STATENAME', ''),
        "Country": customer.get('COUNTRY', ''),
        "Phone": customer.get('PHONE', ''),
        "Fax": customer.get('FAX', ''),
        "Notes": customer.get('NOTES', ''),
        "Links": customer.get('LINKS', ''),
        "Longitude": customer.get('LONGITUDE', 0),
        "Latitude": customer.get('LATITUDE', 0),
        "ZipCodeStr": customer.get('ZIP', '')
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        log_json("ERROR", f"Error creating Atera customer '{customer['CUSTDES']}'", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()

    customer_id = response.json()['ActionID']

    # Now update the 'Priority Customer Number' custom field
    update_atera_custom_field(customer_id, 'Priority Customer Number', customer['CUSTNAME'])

    return response.json()

def update_atera_customer(customer_id, customer):
    """Update an existing customer in Atera."""
    url = f"https://app.atera.com/api/v3/customers/{customer_id}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    data = {
        "CustomerName": customer['CUSTDES'],
        "BusinessNumber": customer.get('BUSINESSNUMBER', ''),
        "Domain": customer.get('DOMAIN', ''),
        "Address": customer.get('ADDRESS', ''),
        "City": customer.get('CITY', ''),
        "State": customer.get('STATENAME', ''),
        "Country": customer.get('COUNTRY', ''),
        "Phone": customer.get('PHONE', ''),
        "Fax": customer.get('FAX', ''),
        "Notes": customer.get('NOTES', ''),
        "Links": customer.get('LINKS', ''),
        "Longitude": customer.get('LONGITUDE', 0),
        "Latitude": customer.get('LATITUDE', 0),
        "ZipCodeStr": customer.get('ZIP', '')
    }

    response = requests.put(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        log_json("ERROR", f"Error updating Atera customer ID {customer_id}", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()

    # Update the 'Priority Customer Number' custom field in case it changed
    update_atera_custom_field(customer_id, 'Priority Customer Number', customer['CUSTNAME'])

    return response.json()

def update_atera_custom_field(customer_id, field_name, value):
    """Update a custom field for a customer in Atera."""
    url = f"https://app.atera.com/api/v3/customvalues/customerfield/{customer_id}/{quote(field_name)}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'text/html'
    }
    data = {"Value": value}
    response = requests.put(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        log_json("ERROR", f"Error updating custom field '{field_name}' for customer ID {customer_id}", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()

def sync_customers():
    """Sync customers from Priority to Atera, performing upsert based on IDs and names."""
    priority_customers = get_priority_customers()
    atera_customers = get_atera_customers()

    # Build mappings:
    # - By 'Priority Customer Number' (ID)
    # - By 'CustomerName' (name)
    atera_customer_id_map = {}    # Mapping from Priority Customer Number to Atera CustomerID
    atera_customer_name_map = {}  # Mapping from CustomerName to Atera CustomerID

    for customer in atera_customers:
        # Map by Priority Customer Number (ID)
        priority_customer_number = customer.get('PriorityCustomerNumber')
        if priority_customer_number:
            atera_customer_id_map[priority_customer_number] = customer['CustomerID']

        # Map by CustomerName (name)
        customer_name = customer.get('CustomerName', '').strip().lower()
        if customer_name:
            atera_customer_name_map[customer_name] = customer['CustomerID']

    log_json("INFO", f"Atera customers by ID", {"atera_customer_id_map": atera_customer_id_map})

    for customer in priority_customers:
        priority_customer_number = customer['CUSTNAME']
        priority_customer_name = customer.get('CUSTDES', '').strip().lower()

        log_json("INFO", f"Processing Priority customer", {"CUSTNAME": priority_customer_number, "CUSTDES": priority_customer_name})

        # Try to find the customer in Atera by Priority Customer Number (ID)
        customer_id = atera_customer_id_map.get(priority_customer_number)

        if customer_id:
            # Customer exists in both systems by ID, perform an update
            log_json("INFO", f"Found matching customer in Atera by ID. Updating customer.", {"CUSTDES": customer['CUSTDES'], "CustomerID": customer_id})
            update_atera_customer(customer_id, customer)
        else:
            # Try to find the customer in Atera by name
            customer_id = atera_customer_name_map.get(priority_customer_name)
            if customer_id:
                # Customer exists in Atera by name, perform an update and set the Priority Customer Number
                log_json("INFO", f"Found matching customer in Atera by name. Updating customer.", {"CUSTDES": customer['CUSTDES'], "CustomerID": customer_id})
                update_atera_customer(customer_id, customer)
            else:
                # Customer does not exist in Atera, create it
                log_json("INFO", f"No matching customer found in Atera. Creating customer.", {"CUSTDES": customer['CUSTDES']})
                result = create_atera_customer(customer)
                log_json("INFO", f"Customer created in Atera.", {"CUSTDES": customer['CUSTDES'], "ActionID": result['ActionID']})

# ------------------- SYNC CONTACTS -------------------
def get_priority_contacts():
    """Fetch contacts from Priority with specific fields."""
    select_fields = 'CUSTNAME,CUSTDES,EMAIL,NAME,FIRSTNAME,LASTNAME,POSITIONDES,PHONENUM,CELLPHONE'
    url = f"{PRIORITY_API_URL}/PHONEBOOK?$select={select_fields}"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching Priority contacts: {response.status_code}", {"response": response.text})
    response.raise_for_status()
    return response.json()['value']

def get_atera_contacts():
    """Fetch all contacts from Atera, handling pagination."""
    contacts = []
    page = 1
    while True:
        url = f"https://app.atera.com/api/v3/contacts?page={page}&itemsInPage=100"
        headers = {
            'X-Api-Key': ATERA_API_KEY,
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            log_json("ERROR", f"Error fetching contacts from Atera", {"status_code": response.status_code, "response": response.text})
            response.raise_for_status()
        data = response.json()
        contacts.extend(data['items'])
        if not data.get('nextLink'):
            break
        page += 1
    return contacts

def sync_contacts():
    """Sync contacts from Priority to Atera, performing upsert based on contact name."""
    # Fetch contacts and customers from both systems
    priority_contacts = get_priority_contacts()
    atera_contacts = get_atera_contacts()
    atera_customers = get_atera_customers()

    # Build a mapping of 'Priority Customer Number' to Atera customer IDs
    atera_customer_map = {}
    for customer in atera_customers:
        priority_customer_number = customer.get('PriorityCustomerNumber')
        if priority_customer_number:
            atera_customer_map[priority_customer_number] = customer['CustomerID']

    # Build a mapping of contacts in Atera based on CustomerID and Full Name
    atera_contact_map = {}
    for contact in atera_contacts:
        customer_id = contact['CustomerID']
        full_name = f"{contact.get('Firstname', '').strip()} {contact.get('Lastname', '').strip()}".strip()
        if customer_id and full_name:
            key = (customer_id, full_name.lower())
            atera_contact_map[key] = contact

    # Now sync contacts
    for contact in priority_contacts:
        try:
            priority_customer_number = contact['CUSTNAME']
            if not priority_customer_number:
                log_json("INFO", "Skipping contact with null CUSTNAME.", {"contact": contact})
                continue
            customer_id = atera_customer_map.get(priority_customer_number)

            first_name = (contact.get('FIRSTNAME') or '').strip()
            last_name = (contact.get('LASTNAME') or '').strip()
            name = (contact.get('NAME') or '').strip()
            # If last name is missing, use first name as last name
            if not last_name:
                last_name = first_name
                if not first_name:
                    first_name = name
                    last_name = ''

            # If both names are missing, skip the contact
            if not first_name and not last_name and not name:
                reason = "Contact with missing name fields."
                log_json("ERROR", reason, {"contact": contact})
                continue

            if not customer_id:
                reason = f"No matching customer in Atera for CUSTNAME '{priority_customer_number}'."
                log_json("ERROR", reason, {"contact": contact})
                continue

            full_name = f"{first_name} {last_name}".strip()
            key = (customer_id, full_name.lower())
            existing_contact = atera_contact_map.get(key)

            # Handle potential null email
            email = contact.get('EMAIL', '')
            if email:
                email = email.strip().lower()
            else:
                # Generate unique email using contact name and customer ID
                sanitized_name = (first_name + last_name).replace(' ', '').lower()
                email = f"{sanitized_name}{customer_id}@example.com"
                log_json("INFO", f"No email for contact '{full_name}'. Generated email.", {"generated_email": email})

            contact['FIRSTNAME'] = first_name
            contact['LASTNAME'] = last_name
            contact['EMAIL'] = email

            # Sanitize phone numbers
            contact['PHONENUM'] = sanitize_phone_number(contact.get('PHONENUM'))
            contact['CELLPHONE'] = sanitize_phone_number(contact.get('CELLPHONE'))

            if existing_contact:
                # Update the contact in Atera
                contact_id = existing_contact['EndUserID']
                update_atera_contact(contact_id, contact)
                log_json("INFO", f"Contact updated in Atera.", {"contact_id": contact_id, "contact_data": contact})
            else:
                # Create the contact in Atera
                create_atera_contact(customer_id, contact)
                log_json("INFO", f"Contact created in Atera.", {"contact_data": contact})
        except Exception as e:
            # Log as ERROR and include full contact data
            log_json("ERROR", f"Error processing contact: {e}", {"contact": contact})
            continue

def create_atera_contact(customer_id, contact):
    """Create a contact in Atera."""
    url = "https://app.atera.com/api/v3/contacts"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    data = {
        "Email": contact['EMAIL'],
        "CustomerID": customer_id,
        "Firstname": contact['FIRSTNAME'] or contact['NAME'],
        "Lastname": contact['LASTNAME'] or contact['NAME'],
        "JobTitle": contact.get('POSITIONDES', ''),
        "Phone": contact.get('PHONENUM', ''),
        "MobilePhone": contact.get('CELLPHONE', ''),
        "IsContactPerson": True,
        "InIgnoreMode": False,
        "CreatedOn": datetime.utcnow().isoformat() + "Z"
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code in [409]:
        # Modify email by appending customer ID before '@' and retry
        email_parts = contact['EMAIL'].split('@')
        if len(email_parts) == 2:
            new_email = f"{email_parts[0]}+{contact['CUSTNAME']}@{email_parts[1]}"
            log_json("INFO", f"Email already exists. Retrying with modified email.", {"original_email": contact['EMAIL'], "new_email": new_email})
            data['Email'] = new_email
            response = requests.post(url, headers=headers, json=data)
            if response.status_code not in [200, 201]:
                # Log as ERROR and include full data sent
                log_json("ERROR", f"Error creating contact with modified email", {"status_code": response.status_code, "response": response.text, "data": data})
                response.raise_for_status()
            else:
                log_json("INFO", f"Contact created with modified email.", {"contact_data": data})
        else:
            # Email format is invalid
            log_json("ERROR", f"Invalid email format for contact", {"contact": contact})
            response.raise_for_status()
    elif response.status_code not in [200, 201]:
        # Log as ERROR and include full data sent
        log_json("ERROR", f"Error creating contact", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()
    else:
        # Contact created successfully
        log_json("INFO", f"Contact created in Atera.", {"contact_data": data})

def update_atera_contact(contact_id, contact):
    """Update an existing contact in Atera."""
    url = f"https://app.atera.com/api/v3/contacts/{contact_id}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    data = {
        "Email": contact['EMAIL'],
        "Firstname": contact['FIRSTNAME'] or contact['NAME'],
        "Lastname": contact['LASTNAME'] or contact['NAME'],
        "JobTitle": contact.get('POSITIONDES', ''),
        "Phone": contact.get('PHONENUM', ''),
        "MobilePhone": contact.get('CELLPHONE', ''),
        "IsContactPerson": True,
        "InIgnoreMode": False
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        # Log as ERROR and include full data sent
        log_json("ERROR", f"Error updating contact ID {contact_id}", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()

# ------------------- MAIN FUNCTION -------------------
def main():
    """Main function to run selected syncs based on config flags."""
    if SYNC_CUSTOMERS:
        log_json("INFO", "Syncing customers from Priority to Atera...")
        sync_customers()
    else:
        log_json("INFO", "Customer sync disabled in config.")

    if SYNC_CONTACTS:
        log_json("INFO", "Syncing contacts from Priority to Atera...")
        sync_contacts()
    else:
        log_json("INFO", "Contact sync disabled in config.")

    if SYNC_CONTRACTS:
        log_json("INFO", "Syncing contracts from Priority to Atera...")
        # sync_contracts()
    else:
        log_json("INFO", "Contract sync disabled in config.")

    if SYNC_SERVICE_CALLS:
        log_json("INFO", "Syncing service calls from Atera to Priority as invoices...")
        # sync_service_calls()
    else:
        log_json("INFO", "Service call sync disabled in config.")

if __name__ == "__main__":
    main()

