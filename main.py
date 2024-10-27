from datetime import datetime
from urllib.parse import quote
import requests

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

# convert to bool from string
SYNC_CUSTOMERS = bool(int(config.get('SYNC_CUSTOMERS', 0)))
SYNC_CONTACTS = bool(int(config.get('SYNC_CONTACTS', False)))
SYNC_CONTRACTS = bool(int(config.get('SYNC_CONTRACTS', False)))
SYNC_SERVICE_CALLS = bool(int(config.get('SYNC_SERVICE_CALLS', False)))


# ------------------- SYNC CUSTOMERS -------------------
def get_priority_customers():
    """Fetch customers from Priority with specific fields."""
    select_fields = 'CUSTNAME,CUSTDES,HOSTNAME,WTAXNUM,PHONE,FAX,ADDRESS,STATEA,STATENAME,STATE,ZIP'
    url = f"{PRIORITY_API_URL}/CUSTOMERS?$select={select_fields}"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
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
        print(f"Fetching customers from Atera, page {page}...")
        params = {'page': page, 'itemsInPage': items_in_page}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            response.raise_for_status()
        data = response.json()
        items = data.get('items', [])
        if not items:
            break
        customers.extend(items)
        page += 1

    # Now fetch the 'Priority Customer Number' custom field for each customer
    for customer in customers:
        print(f"Fetching custom field for customer ID {customer['CustomerID']}...")
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
        return response.json()[0]['ValueAsString']  # The response is a JSON string with quotes
    elif response.status_code == 404:
        # Field not found for this customer
        return None
    else:
        print(
            f"Error fetching custom field '{field_name}' for customer ID {customer_id}: {response.status_code} - {response.text}")
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
        print(f"Error {response.status_code}: {response.text}")
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
        print(f"Error updating customer ID {customer_id}: {response.status_code} - {response.text}")
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
        print(
            f"Error updating custom field '{field_name}' for customer ID {customer_id}: {response.status_code} - {response.text}")
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

    print(f"Atera customers by ID: {atera_customer_id_map}")

    for customer in priority_customers:
        priority_customer_number = customer['CUSTNAME']
        priority_customer_name = customer.get('CUSTDES', '').strip().lower()

        print(f"Processing Priority customer: CUSTNAME={priority_customer_number}, CUSTDES={priority_customer_name}")

        # Try to find the customer in Atera by Priority Customer Number (ID)
        customer_id = atera_customer_id_map.get(priority_customer_number)

        if customer_id:
            # Customer exists in both systems by ID, perform an update
            print(f"Found matching customer in Atera by ID. Updating customer '{customer['CUSTDES']}' in Atera (ID: {customer_id}) by ID.")
            update_atera_customer(customer_id, customer)
        else:
            # Try to find the customer in Atera by name
            customer_id = atera_customer_name_map.get(priority_customer_name)
            if customer_id:
                # Customer exists in Atera by name, perform an update and set the Priority Customer Number
                print(f"Found matching customer in Atera by name. Updating customer '{customer['CUSTDES']}' in Atera (ID: {customer_id}) by name.")
                update_atera_customer(customer_id, customer)
            else:
                # Customer does not exist in Atera, create it
                print(f"No matching customer found in Atera. Creating customer '{customer['CUSTDES']}' in Atera.")
                result = create_atera_customer(customer)
                print(f"Customer '{customer['CUSTDES']}' created in Atera with ID {result['ActionID']}.")


# ------------------- SYNC CONTACTS -------------------
def get_priority_contacts():
    """Fetch contacts from Priority with specific fields."""
    select_fields = 'CUSTNAME,CUSTDES,EMAIL,FIRSTNAME,LASTNAME,POSITIONDES,PHONENUM,CELLPHONE'
    url = f"{PRIORITY_API_URL}/PHONEBOOK?$select={select_fields}"
    response = requests.get(url, auth=(PRIORITY_API_USER, PRIORITY_API_PASSWORD))
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
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
            print(f"Error fetching contacts from Atera: {response.status_code} - {response.text}")
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
        priority_customer_number = contact['CUSTNAME']
        customer_id = atera_customer_map.get(priority_customer_number)

        if not customer_id:
            print(
                f"No matching customer in Atera for CUSTNAME '{priority_customer_number}'. Skipping contact '{contact.get('FIRSTNAME', '')} {contact.get('LASTNAME', '')}'.")
            continue

        first_name = (contact.get('FIRSTNAME') or '').strip()
        last_name = (contact.get('LASTNAME') or '').strip()

        # If last name is missing, use first name as last name
        if not last_name:
            last_name = first_name

        # If both names are missing, skip the contact
        if not first_name and not last_name:
            print(f"Contact with missing name fields. Skipping contact with email '{contact.get('EMAIL', '')}'.")
            continue

        full_name = f"{first_name} {last_name}".strip()
        key = (customer_id, full_name.lower())
        existing_contact = atera_contact_map.get(key)

        email = contact.get('EMAIL', '').strip()
        if not email:
            # Generate unique email using contact name and customer ID
            sanitized_name = (first_name + last_name).replace(' ', '').lower()
            email = f"{sanitized_name}{customer_id}@example.com"
            print(f"No email for contact '{full_name}'. Generated email: {email}")

        contact['FIRSTNAME'] = first_name
        contact['LASTNAME'] = last_name
        contact['EMAIL'] = email

        if existing_contact:
            # Update the contact in Atera
            contact_id = existing_contact['EndUserID']
            print(f"Updating contact '{full_name}' in Atera (ID: {contact_id}).")
            update_atera_contact(contact_id, contact)
        else:
            # Create the contact in Atera
            print(f"Creating contact '{full_name}' in Atera.")
            create_atera_contact(customer_id, contact)


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
        "Firstname": contact['FIRSTNAME'],
        "Lastname": contact['LASTNAME'],
        "JobTitle": contact.get('POSITIONDES', ''),
        "Phone": contact.get('PHONENUM', ''),
        "MobilePhone": contact.get('CELLPHONE', ''),
        "IsContactPerson": True,
        "InIgnoreMode": False,
        "CreatedOn": datetime.utcnow().isoformat() + "Z"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        print(
            f"Error creating contact '{contact['FIRSTNAME']} {contact['LASTNAME']}': {response.status_code} - {response.text}")
        response.raise_for_status()
    else:
        print(f"Contact '{contact['FIRSTNAME']} {contact['LASTNAME']}' created in Atera.")


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
        "Firstname": contact['FIRSTNAME'],
        "Lastname": contact['LASTNAME'],
        "JobTitle": contact.get('POSITIONDES', ''),
        "Phone": contact.get('PHONENUM', ''),
        "MobilePhone": contact.get('CELLPHONE', ''),
        "IsContactPerson": True,
        "InIgnoreMode": False
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code not in [200, 201]:
        print(f"Error updating contact ID {contact_id}: {response.status_code} - {response.text}")
        response.raise_for_status()
    else:
        print(f"Contact ID {contact_id} updated in Atera.")


# ------------------- MAIN FUNCTION -------------------

def main():
    """Main function to run selected syncs based on config flags."""
    if SYNC_CUSTOMERS:
        print("Syncing customers from Priority to Atera...")
        sync_customers()
    else:
        print("Customer sync disabled in config.")

    if SYNC_CONTACTS:
        print("Syncing contacts from Priority to Atera...")
        sync_contacts()
    else:
        print("Contact sync disabled in config.")

    if SYNC_CONTRACTS:
        print("Syncing contracts from Priority to Atera...")
        # sync_contracts()
    else:
        print("Contract sync disabled in config.")

    if SYNC_SERVICE_CALLS:
        print("Syncing service calls from Atera to Priority as invoices...")
        # sync_service_calls()
    else:
        print("Service call sync disabled in config.")


if __name__ == "__main__":
    main()
