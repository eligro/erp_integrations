# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from urllib.parse import quote
import requests
import logging
import os
import json  # For JSON formatting in logs
import re    # For phone number sanitization
import csv

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
# DELETE_ALL_CUSTOMERS = bool(int(config.get('DELETE_ALL_CUSTOMERS', 0)))
SYNC_TICKETS = bool(int(config.get('SYNC_TICKETS', 0)))  # New sync option
DAYS_BACK_TICKETS = int(config.get('DAYS_BACK_TICKETS', 2))  # Days back to fetch tickets
PULL_PERIOD_DAYS = int(config.get('PULL_PERIOD_DAYS', 2))

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
    select_fields = 'CUSTNAME,CUSTDES,HOSTNAME,WTAXNUM,PHONE,FAX,ADDRESS,STATDES,STATEA,STATENAME,STATE,ZIP'
    url = f"{PRIORITY_API_URL}/CUSTOMERS?$select={select_fields}"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching Priority customers: {response.status_code}", {"response": response.text})
    response.raise_for_status()
    return response.json()['value']

def get_atera_customers(fetch_custom_fields=True):
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
        customers.extend(items)
        if int(data['totalPages']) == page or not items:
            break
        page += 1

    if not fetch_custom_fields:
        return customers
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


def log_failed_duplicate_email(customer_id, priority_customer_id, email):
    """Log failed duplicate emails to a CSV file."""
    file_path = 'failed_duplicated_emails.csv'
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            # Write header if the file doesn't exist
            writer.writerow(['CustomerID', 'PriorityCustomerID', 'EmailAddress'])
        # Write the failed email
        writer.writerow([customer_id, priority_customer_id, email])

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
    if response.status_code == 409:
        # Log the duplicate email issue along with the Priority Customer ID
        priority_customer_id = contact.get('CUSTNAME', '')
        log_json("INFO", f"Email already exists for customer.", {"CustomerID": customer_id, "PriorityCustomerID": priority_customer_id, "Email": contact['EMAIL']})
        log_failed_duplicate_email(customer_id, priority_customer_id, contact['EMAIL'])
    elif response.status_code not in [200, 201]:
        log_json("ERROR", f"Error creating contact", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()
    else:
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

# def delete_all_atera_customers():
#     """Fetch all customers from Atera and delete them."""
#     atera_customers = get_atera_customers(fetch_custom_fields=False)  # Fetch all customers
#     for customer in atera_customers:
#         customer_id = customer['CustomerID']
#         log_json("INFO", f"Deleting customer from Atera.", {"CustomerID": customer_id, "CustomerName": customer.get('CustomerName', '')})
#         delete_atera_customer(customer_id)

# def delete_atera_customer(customer_id):
#     """Delete a customer from Atera."""
#     url = f"https://app.atera.com/api/v3/customers/{customer_id}"
#     headers = {
#         'X-Api-Key': ATERA_API_KEY,
#         'Accept': 'application/json'
#     }
#     response = requests.delete(url, headers=headers)
#     if response.status_code == 204:
#         log_json("INFO", f"Customer deleted successfully.", {"CustomerID": customer_id})
#     else:
#         log_json("ERROR", f"Error deleting customer ID {customer_id}", {"status_code": response.status_code, "response": response.text})

def get_atera_tickets(days_back):
    # Get tickets from Atera created in the last X days
    # We'll fetch all tickets and filter by creation date.
    # API: GET /api/v3/tickets
    # We'll paginate just in case. Max 50 per page.
    url = "https://app.atera.com/api/v3/tickets"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'application/json'
    }
    tickets = []
    page = 1
    items_in_page = 50
    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    while True:
        params = {
            'page': page,
            'itemsInPage': items_in_page
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log_json("ERROR", "Error fetching tickets from Atera", {"status_code": response.status_code, "response": response.text})
            response.raise_for_status()

        data = response.json()
        fetched_items = data.get('items', [])
        if not fetched_items:
            break
        for ticket in fetched_items:
            created_date_str = ticket.get('TicketCreatedDate')
            if created_date_str:
                if "+" in created_date_str:
                    # remove the offset part
                    created_date = datetime.fromisoformat(created_date_str.split("+")[0])
                elif "Z" in created_date_str:
                    # remove the Z part
                    created_date = datetime.fromisoformat(created_date_str.replace("Z", ""))
                else:
                    created_date = datetime.fromisoformat(created_date_str)
                print(created_date)
                print(cutoff_date)
                if created_date >= cutoff_date:
                    tickets.append(ticket)
        if not data.get('nextLink'):
            break
        page += 1
    return tickets

def send_ticket_to_priority(custname, docno, tquant, ticket_status, payment_type):
    # POST to Priority endpoint MARH_LOADATERA
    url = f"{PRIORITY_API_URL}/MARH_LOADATERA"
    headers = {
        'Content-Type': 'application/json'
    }
    auth = (PRIORITY_API_USER, PRIORITY_API_PASSWORD)
    data = {
        "CUSTNAME": custname,
        "ATERADOCNO": docno,
        "TQUANT": tquant,
        "ATERASTATUS": ticket_status,
        "ATERATICKETTYPE": payment_type,
    }
    response = requests.post(url, headers=headers, auth=auth, json=data)
    if response.status_code not in [200, 201]:
        log_json("ERROR", "Error sending ticket to Priority", {"status_code": response.status_code, "response": response.text, "data": data})
        response.raise_for_status()
    else:
        log_json("INFO", "Ticket sent to Priority", {"data": data})

def get_atera_customer(customer_id):
    """
    Fetch a single customer record from Atera by customer_id.
    Returns the raw JSON object for that customer or raises if not found.
    """
    url = f"https://app.atera.com/api/v3/customers/{customer_id}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        # Not found
        return None
    if response.status_code != 200:
        log_json("ERROR", "Error fetching single Atera customer", {
            "status_code": response.status_code,
            "response": response.text,
            "customer_id": customer_id
        })
        response.raise_for_status()
    return response.json()


def get_atera_customer_custom_field(customer_id, field_name):
    """
    Fetch a single custom field by name for a given Atera customer_id.
    Returns the field's value or None if 404 or field does not exist.
    """
    url = f"https://app.atera.com/api/v3/customvalues/customerfield/{customer_id}/{quote(field_name)}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        # Custom field not found
        return None
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching custom field '{field_name}' for customer ID {customer_id}", {
            "status_code": response.status_code,
            "response": response.text
        })
        response.raise_for_status()
    # According to Atera docs, the response should be a list with at least one item:
    data = response.json()
    if not data:
        return None
    return data[0].get('ValueAsString')

def get_atera_ticket_custom_field(ticket_id, field_name):
    """Fetch a custom field value for a given ticket."""
    url = f"https://app.atera.com/api/v3/customvalues/ticketfield/{ticket_id}/{quote(field_name)}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    if not data or 'ValueAsString' not in data[0]:
        return None
    return data[0]['ValueAsString']  # or data[0]['ValueAsDecimal'] if you prefer

def sync_tickets():
    """
    In this revised version, we no longer fetch all Atera customers at once.
    Instead, we create a cache dict and fetch customers on demand based on the
    tickets' CustomerID. This avoids long loading times for large customer bases.
    """
    log_json("INFO", "Syncing tickets from Atera to Priority...")

    # 1. Fetch tickets from Atera created in the last DAYS_BACK_TICKETS days
    tickets = get_atera_tickets(DAYS_BACK_TICKETS)
    if not tickets:
        log_json("INFO", "No tickets found for syncing.")
        return

    # 2. Prepare a local cache for mapping Atera CustomerID => Priority CUSTNAME
    priority_customer_cache = {}  # { customer_id: "CUSTNAME" }

    for ticket in tickets:
        customer_id = ticket.get('CustomerID')
        if not customer_id:
            log_json("ERROR", "Ticket does not have a CustomerID; cannot sync.", {
                "TicketID": ticket.get('TicketID')
            })
            continue

        # If we have not already cached this customer's Priority Customer Number:
        if customer_id not in priority_customer_cache:
            # Fetch the single Atera customer
            atera_customer = get_atera_customer(customer_id)
            if not atera_customer:
                log_json("ERROR",
                         "No customer record found in Atera for this ticket's CustomerID",
                         {"TicketID": ticket.get('TicketID'), "CustomerID": customer_id})
                # We can store an empty string or None to avoid repeated lookups
                priority_customer_cache[customer_id] = None
                continue

            # Fetch the "Priority Customer Number" custom field
            priority_customer_number = get_atera_customer_custom_field(
                customer_id,
                "Priority Customer Number"
            )

            # Cache the result (could be None if the field doesn't exist)
            priority_customer_cache[customer_id] = priority_customer_number

        # At this point we have a Priority CUSTNAME (or None) in the cache
        custname = priority_customer_cache[customer_id]
        if not custname:
            log_json("ERROR",
                     "No Priority customer number found for ticket (custom field is empty).",
                     {"TicketID": ticket.get('TicketID'), "CustomerID": customer_id})
            continue

        # 3. Prepare the data to send to Priority
        ticket_status = ticket['TicketStatus']
        docno = str(ticket.get('TicketID'))

        # Fetch the custom field Technician Billable Hours
        tech_hours_str = get_atera_ticket_custom_field(ticket.get('TicketID'), "Technician Billable Hours")
        payment_type = get_atera_ticket_custom_field(ticket.get('TicketID'), "Payment")
        if not tech_hours_str:
            # Fall back to 0 if missing or error
            tquant = 0
            log_json("ERROR", "Failed to fetch Technician Billable Hours custom field.", {
                "TicketID": ticket.get('TicketID')
            })
        else:
            try:
                tquant = float(tech_hours_str)
            except ValueError:
                log_json("ERROR", "Failed to parse Technician Billable Hours custom field as float.", {
                    "TicketID": ticket.get('TicketID'),
                    "TechHoursValue": tech_hours_str
                })
                tquant = 0

        send_ticket_to_priority(custname, docno, tquant, ticket_status, payment_type)


def get_priority_contracts_mock():
    return [
        {
            'CUSTNAME': 'T003283',
            'CUSTDES': 'Customer One',
            'DOCNO': 'CONTRACT001',
            'UDATE': datetime.utcnow().isoformat() + 'Z',  # updated now
            'VALIDDATE': '2025-02-01T00:00:00Z',
            'EXPIRYDATE': '2025-12-31T00:00:00Z',
            'STATDES': 'Active',
            'UNI_DESC': 'Sample Contract'
        }
    ]

def get_priority_contracts():
    """
    Fetch contracts from Priority, then filter by UDATE within PULL_PERIOD_DAYS.
    Example response fields: CUSTNAME, CUSTDES, DOCNO, UDATE, VALIDDATE, EXPIRYDATE, STATDES, UNI_DESC
    """
    url = f"{PRIORITY_API_URL}/DOCUMENTS_Z"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching Priority contracts: {response.status_code}", {"response": response.text})
        response.raise_for_status()
    all_contracts = response.json().get('value', [])

    # Filter by UDATE in last PULL_PERIOD_DAYS
    cutoff = datetime.utcnow() - timedelta(days=PULL_PERIOD_DAYS)
    filtered = []
    for c in all_contracts:
        try:
            # The Priority response might have an offset, handle that
            udate_str = c.get('UDATE')
            if not udate_str:
                continue
            # remove possible offset or 'Z'
            if '+' in udate_str:
                udate_str = udate_str.split('+')[0]
            elif 'Z' in udate_str:
                udate_str = udate_str.replace('Z', '')
            contract_udate = datetime.fromisoformat(udate_str)

            if contract_udate >= cutoff:
                filtered.append(c)
        except Exception as e:
            log_json("ERROR", "Error parsing UDATE", {"exception": str(e), "contract": c})
    return filtered

def get_atera_contracts_for_customer(customer_id):
    """
    Pull all existing contracts in Atera for a specific customer.
    We'll page through if needed.
    """
    url = f"https://app.atera.com/api/v3/contracts/customer/{customer_id}"
    headers = {'X-Api-Key': ATERA_API_KEY, 'Accept': 'application/json'}
    contracts = []
    page = 1
    items_in_page = 50

    while True:
        params = {'page': page, 'itemsInPage': items_in_page}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            log_json("ERROR", "Error fetching Atera contracts", {
                "status_code": response.status_code,
                "response": response.text
            })
            response.raise_for_status()
        data = response.json()
        page_contracts = data.get('items', [])
        if not page_contracts:
            break
        contracts.extend(page_contracts)
        if not data.get('nextLink'):
            break
        page += 1
    return contracts


def create_atera_contract(customer_id, contract):
    """
    Create a new contract in Atera.
    Use contract['DOCNO'] => Priority Contract Number custom field later.
    """
    url = "https://app.atera.com/api/v3/contracts"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    # If STATDES == '?????' => set Active = False
    active = contract.get('STATDES') != "מבוטל"
    if not active:
        log_json("INFO", "Skipping contract with inactive STATDES.", {"contract": contract})
        return
    # Fall back to a name if UNI_DESC is missing
    contract_name = contract.get('UNI_DESC') or f"Contract {contract.get('DOCNO', '')}"

    # Format the dates for Atera. Remove +offset if present.
    start_date_str = contract.get('VALIDDATE')
    end_date_str = contract.get('EXPIRYDATE')

    data = {
        "ContractName": contract_name,
        "CustomerID": customer_id,
        "StartDate": start_date_str,
        "EndDate": end_date_str,
        "Active": active,
        "Taxable": True,
        "ContractType": "RetainerFlatFee",  # pick any default
        "RetainerFlatFeeContract": {
            "RateID": 1,
            "Quantity": 1,
            "BillingPeriod": "Monthly"
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        log_json("ERROR", "Error creating contract in Atera", {
            "status_code": response.status_code,
            "response": response.text,
            "payload": data
        })
        response.raise_for_status()

    created_id = response.json().get('ActionID')
    if created_id:
        # Update custom field "Priority Contract Number" with DOCNO
        update_atera_contract_custom_field(created_id, "Priority Contract Number", contract['DOCNO'])
        log_json("INFO", f"Created contract in Atera for Priority DOCNO={contract['DOCNO']}", {"ContractID": created_id})

    return response.json()

def update_atera_contract_custom_field(contract_id, field_name, value):
    """
    Same pattern as updating a custom field on a customer, but for contracts.
    If the route is /api/v3/customvalues/contractfield/{contractId}/{fieldName}, do:
    """
    url = f"https://app.atera.com/api/v3/customvalues/contractfield/{contract_id}/{quote(field_name)}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'text/html'
    }
    data = {"Value": value}
    response = requests.put(url, headers=headers, json=data)
    if response.status_code not in [200,201]:
        log_json("ERROR", "Error updating contract custom field", {
            "status_code": response.status_code,
            "response": response.text,
            "data": data
        })
        response.raise_for_status()


def get_atera_contract_custom_field(contract_id, field_name):
    """
    Fetches a custom field value (ValueAsString) for a given contract in Atera.
    """
    url = f"https://app.atera.com/api/v3/customvalues/contractfield/{contract_id}/{quote(field_name)}"
    headers = {
        'X-Api-Key': ATERA_API_KEY,
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        log_json("ERROR", f"Error fetching contract custom field '{field_name}' for contract ID {contract_id}", {
            "status_code": response.status_code,
            "response": response.text
        })
        response.raise_for_status()
    data = response.json()
    if not data or 'ValueAsString' not in data[0]:
        return None
    return data[0]['ValueAsString']


def sync_contracts():
    log_json("INFO", "Syncing contracts from Priority to Atera...")

    # 1) Get all Priority customers so we can check if customer is active
    priority_customers_list = get_priority_customers()
    # Map them by CUSTDES for quick lookup
    priority_customers_map = {c['CUSTDES']: c for c in priority_customers_list}

    # 2) Fetch relevant contracts
    priority_contracts = get_priority_contracts()
    # priority_contracts = get_priority_contracts_mock()
    if not priority_contracts:
        log_json("INFO", "No Priority contracts found for the given period.")
        return

    # Build map of Priority -> Atera customer IDs
    atera_customers = get_atera_customers()
    cust_map = { c.get('PriorityCustomerNumber'): c['CustomerID']
                 for c in atera_customers if c.get('PriorityCustomerNumber') }

    for contract in priority_contracts:
        custname = contract.get('CUSTNAME')
        custdes = contract.get('CUSTDES', '')  # We'll look up the customer by CUSTDES
        doc_no = contract.get('DOCNO')

        if not custname or not doc_no:
            log_json("ERROR", "Missing CUSTNAME or DOCNO in contract, skipping", {"contract": contract})
            continue

        # Check if the Priority customer is active (STATDES == 'פעיל')
        priority_cust = priority_customers_map.get(custdes)
        if not priority_cust:
            log_json("ERROR", "No matching customer in Priority", {"CUSTDES": custdes, "contract": contract})
            continue

        if priority_cust.get('STATDES') != 'פעיל':
            log_json("INFO", "Skipping contract because customer is not active.", {
                "CUSTDES": custdes,
                "contract": contract
            })
            continue

        # Check if contract itself is active (STATDES != 'מבוטל')
        if contract.get('STATDES') == 'מבוטל':
            log_json("INFO", "Skipping contract because contract STATDES is מבוטל.", {
                "DOCNO": doc_no
            })
            continue

        # Map the Priority customer to Atera CustomerID
        customer_id = cust_map.get(custname)
        if not customer_id:
            log_json("ERROR", f"No matching Atera customer for Priority {custname}", {"contract": contract})
            continue

        # Fetch existing Atera contracts
        atera_contracts = get_atera_contracts_for_customer(customer_id)
        # Check if DOCNO exists
        exists = False
        a_contract_id = None
        for a_contract in atera_contracts:
            a_contract_id = a_contract['ContractID']
            a_contract_docno = get_atera_contract_custom_field(a_contract_id, "Priority Contract Number")
            if a_contract_docno == doc_no:
                exists = True
                break

        if exists:
            log_json("INFO", "Contract already exists in Atera, skipping", {
                "PriorityDOCNO": doc_no,
                "AteraContractID": a_contract_id
            })
        else:
            log_json("INFO", "Creating contract in Atera", {"contract": contract})
            create_atera_contract(customer_id, contract)

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
        sync_contracts()
    else:
        log_json("INFO", "Contract sync disabled in config.")

    if SYNC_SERVICE_CALLS:
        log_json("INFO", "Syncing service calls from Atera to Priority as invoices...")
        # sync_service_calls()
    else:
        log_json("INFO", "Service call sync disabled in config.")

    # if DELETE_ALL_CUSTOMERS:
    #     log_json("INFO", "Deleting all customers in Atera...")
    #     delete_all_atera_customers()
    # else:
    #     log_json("INFO", "Delete all customers disabled in config.")

    if SYNC_TICKETS:
        sync_tickets()
    else:
        log_json("INFO", "Ticket sync disabled in config.")

if __name__ == "__main__":
    main()

