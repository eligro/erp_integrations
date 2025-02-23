from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import patch, call

from main import sync_contracts, sync_customers, sync_contacts, sync_tickets

# Test for syncing customers
def test_sync_customers_update(mocker):
    # Define test data
    priority_customer = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'PHONE': '1234567890',
                'ADDRESS': '123 Main St',
                'STATE': 'CA',
                'ZIP': '90001',
                'MARH_UDATE': datetime.utcnow().isoformat() + 'Z'  # Add MARH_UDATE
            }
        ]
    }

    atera_customer = {
        'totalPages': 1,
        'totalItemCount': 1,
        'itemsInPage': 1,
        'items': [
            {
                'CustomerID': 1,
                'CustomerName': 'Customer One',
                'PriorityCustomerNumber': None,
            }
        ]
    }

    # Mock responses for requests.get
    def mock_get_side_effect(url, *args, **kwargs):
        if 'CUSTOMERS' in url:  # Adjusted to handle any URL containing 'CUSTOMERS'
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = priority_customer
            return response
        elif url == "https://app.atera.com/api/v3/customers":
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_customer
            return response
        elif url.startswith("https://app.atera.com/api/v3/customvalues/customerfield/"):
            response = mocker.MagicMock()
            response.status_code = 404  # Custom field not found
            return response
        else:
            raise ValueError(f"Unhandled URL: {url}")

    # Apply the side effect to the patched get requests
    mocker.patch('main.requests.get', side_effect=mock_get_side_effect)
    mock_put = mocker.patch('main.requests.put')
    mock_post = mocker.patch('main.requests.post')
    mock_put.return_value = mocker.MagicMock(status_code=200)
    mock_post.return_value = mocker.MagicMock(status_code=200, json=lambda: {'ActionID': 1})

    # Run initial sync
    sync_customers()

    # Verify PUT request to update customer in Atera
    expected_put_url = "https://app.atera.com/api/v3/customers/1"
    mock_put.assert_any_call(
        expected_put_url,
        headers={'X-Api-Key': mocker.ANY, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        json={
            "CustomerName": "Customer One",
            "BusinessNumber": "",
            "Domain": "",
            "Address": "123 Main St",
            "City": "",
            "State": "",
            "Country": "",
            "Phone": "1234567890",
            "Fax": "",
            "Notes": "",
            "Links": "",
            "Longitude": 0,
            "Latitude": 0,
            "ZipCodeStr": "90001"
        }
    )

    # Verify PUT request to update 'Priority Customer Number' custom field
    expected_custom_field_url = "https://app.atera.com/api/v3/customvalues/customerfield/1/Priority%20Customer%20Number"
    mock_put.assert_any_call(
        expected_custom_field_url,
        headers={'X-Api-Key': mocker.ANY, 'Content-Type': 'application/json', 'Accept': 'text/html'},
        json={"Value": "CUST001"}
    )

    # Modify Priority customer data
    priority_customer_updated = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'PHONE': '0987654321',  # Changed phone number
                'ADDRESS': '123 Main St',
                'STATE': 'CA',
                'ZIP': '90001',
                'MARH_UDATE': datetime.utcnow().isoformat() + 'Z'  # Add MARH_UDATE
            }
        ]
    }

    # Update mock responses for the modified data
    def mock_get_side_effect_updated(url, *args, **kwargs):
        if 'CUSTOMERS' in url:
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = priority_customer_updated
            return response
        elif url == "https://app.atera.com/api/v3/customers":
            updated_atera_customer = {
                'totalPages': 1,
                'totalItemCount': 1,
                'itemsInPage': 1,
                'items': [
                    {
                        'CustomerID': 1,
                        'CustomerName': 'Customer One',
                        'PriorityCustomerNumber': 'CUST001',
                    }
                ]
            }
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = updated_atera_customer
            return response
        elif url.startswith("https://app.atera.com/api/v3/customvalues/customerfield/"):
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = [{'ValueAsString': 'CUST001'}]
            return response
        else:
            raise ValueError(f"Unhandled URL: {url}")

    mocker.patch('main.requests.get', side_effect=mock_get_side_effect_updated)

    # Reset mocks
    mock_put.reset_mock()
    mock_post.reset_mock()

    # Run sync again
    sync_customers()

    # Verify that the customer was updated with new phone number
    mock_put.assert_any_call(
        expected_put_url,
        headers={'X-Api-Key': mocker.ANY, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        json={
            "CustomerName": "Customer One",
            "BusinessNumber": "",
            "Domain": "",
            "Address": "123 Main St",
            "City": "",
            "State": "",
            "Country": "",
            "Phone": "0987654321",  # Updated phone number
            "Fax": "",
            "Notes": "",
            "Links": "",
            "Longitude": 0,
            "Latitude": 0,
            "ZipCodeStr": "90001"
        }
    )

    print("Customer sync test passed.")

# Test for syncing contacts
def test_sync_contacts_create_partial(mocker):
    # Mock Priority API URL
    mocker.patch('main.PRIORITY_API_URL', 'http://test-priority-api')

    # Define test data
    priority_contacts = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'EMAIL': '',  # Missing email
                'NAME': 'Alice',  # Use NAME instead of FIRSTNAME/LASTNAME
                'FIRSTNAME': 'Alice',
                'LASTNAME': '',  # Missing last name
                'POSITIONDES': 'Manager',
                'PHONENUM': '',
                'CELLPHONE': ''
            },
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'EMAIL': 'bob@example.com',
                'NAME': 'Bob Smith',  # Use NAME instead of FIRSTNAME/LASTNAME
                'FIRSTNAME': '',
                'LASTNAME': 'Smith',  # Missing first name
                'POSITIONDES': 'Engineer',
                'PHONENUM': '555-1234',
                'CELLPHONE': ''
            },
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'EMAIL': '',  # Missing email
                'NAME': '',  # Missing both names
                'FIRSTNAME': '',
                'LASTNAME': '',
                'POSITIONDES': 'Technician',
                'PHONENUM': '',
                'CELLPHONE': ''
            }
        ]
    }

    atera_customers = {
        'totalPages': 1,
        'totalItemCount': 1,
        'itemsInPage': 1,
        'items': [
            {
                'CustomerID': 1,
                'CustomerName': 'Customer One',
                'PriorityCustomerNumber': 'CUST001',
            }
        ]
    }

    atera_contacts = {
        'items': [],
        'totalPages': 1,
        'totalItemCount': 0,
        'itemsInPage': 0
    }

    # Mock responses for requests.get
    def mock_get_side_effect(url, *args, **kwargs):
        if 'PHONEBOOK' in url:
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = priority_contacts
            return response
        elif url.startswith("https://app.atera.com/api/v3/contacts"):
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_contacts
            return response
        elif url == "https://app.atera.com/api/v3/customers":
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_customers
            return response
        elif url.startswith("https://app.atera.com/api/v3/customvalues/customerfield/"):
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = [{'ValueAsString': 'CUST001'}]
            return response
        else:
            raise ValueError(f"Unhandled URL: {url}")

    mocker.patch('main.requests.get', side_effect=mock_get_side_effect)
    mock_post = mocker.patch('main.requests.post')
    mock_put = mocker.patch('main.requests.put')
    mock_post.return_value = mocker.MagicMock(status_code=200, json=lambda: {'ActionID': 2})
    mock_put.return_value = mocker.MagicMock(status_code=200)

    # Run sync
    sync_contacts()

    # Verify that two contacts were created
    create_calls = [
        call for call in mock_post.call_args_list
        if call.args[0] == "https://app.atera.com/api/v3/contacts"
    ]
    assert len(create_calls) == 2, "Expected 2 contacts to be created."

    # Check data for first contact (Alice)
    data_alice = create_calls[0].kwargs['json']
    assert data_alice['Firstname'] == 'Alice'
    assert data_alice['Lastname'] == 'Alice'  # Last name missing, use first name
    assert data_alice['Email'] == 'alicealice1@example.com'  # Generated email

    # Check data for second contact (Smith)
    data_smith = create_calls[1].kwargs['json']
    assert data_smith['Firstname'] == 'Bob Smith'  # First name missing
    assert data_smith['Lastname'] == 'Smith'
    assert data_smith['Email'] == 'bob@example.com'  # Provided email

    print("Contacts sync test passed.")

def test_sync_tickets(mocker):
    # Configure the cutoff date
    days_back = 2
    cutoff_date = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=days_back)
    # Mock ticket creation date to be recent
    recent_date_str = datetime.utcnow().isoformat()

    # Mocked tickets from Atera (created in the last 2 days)
    atera_tickets_response = {
        "items": [
            {
                "TicketID": 123,
                "CustomerID": 10,
                "TicketCreatedDate": recent_date_str,
                "OnSiteDurationMinutes": 120,
                "OffSiteDurationMinutes": 30,
                "TicketStatus": "Active"
            }
        ],
        "totalItemCount": 1,
        "page": 1,
        "itemsInPage": 1,
        "totalPages": 1,
        "prevLink": None,
        "nextLink": None
    }

    # Mocked Atera customers
    atera_customers_response = {
        "items": [
            {
                "CustomerID": 10,
                "CustomerName": "Test Customer",
                "PriorityCustomerNumber": "CUST002"
            }
        ],
        "totalPages": 1,
        "totalItemCount": 1,
        "itemsInPage": 1
    }

    # Mock GET requests
    def mock_get_side_effect(url, *args, **kwargs):
        if "tickets" in url and not "ticketfield" in url:
            # Tickets from Atera
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_tickets_response
            return response
        elif "customers" in url and "customervalues" not in url:
            # Atera customers
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_customers_response
            return response
        elif "customerfield" in url:
            # Custom field fetch
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = [{'ValueAsString': 'CUST002'}]
            return response
        elif "ticketfield" in url:
            # Handle ticket custom field requests
            response = mocker.MagicMock()
            response.status_code = 200
            if "Technician%20Billable%20Hours" in url:
                response.json.return_value = [{'ValueAsString': '2.5'}]
            elif "Payment" in url:
                response.json.return_value = [{'ValueAsString': 'Regular'}]
            return response
        else:
            raise ValueError(f"Unhandled URL: {url}")

    mocker.patch('main.requests.get', side_effect=mock_get_side_effect)

    # Mock POST requests (to Priority and maybe Atera if needed)
    mock_post = mocker.patch('main.requests.post')
    # Priority response
    mock_priority_response = mocker.MagicMock()
    mock_priority_response.status_code = 201
    mock_priority_response.json.return_value = {}
    mock_post.return_value = mock_priority_response

    # Run the sync_tickets function
    sync_tickets()

    # Check that a POST request was made to Priority
    expected_data = {
        "CUSTNAME": "CUST002",
        "ATERADOCNO": "123",
        "TQUANT": 2.5,
        "ATERASTATUS": "Active",
        "ATERATICKETTYPE": "Regular"
    }

    # Verify the call was made with the expected data
    priority_call = None
    for call in mock_post.call_args_list:
        url = call.args[0]
        if 'MARH_LOADATERA' in url:
            priority_call = call
            break

    assert priority_call is not None, "Expected a call to Priority MARH_LOADATERA endpoint."
    assert priority_call.kwargs['json'] == expected_data, "Data sent to Priority does not match expected."
    print("Tickets sync test passed.")

def test_sync_contracts_create_new(mocker):
    """
    Test that a new contract from Priority is created in Atera
    if no matching 'Priority Contract Number' is found.
    """
    # Mock Priority API URL
    mocker.patch('main.PRIORITY_API_URL', 'http://test-priority-api')

    # Priority contracts (one contract) - updated recently
    priority_contracts = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'DOCNO': 'CONTRACT001',
                'UDATE': datetime.utcnow().isoformat() + 'Z',  # updated now
                'VALIDDATE': '2025-02-01T00:00:00Z',
                'EXPIRYDATE': '2025-12-31T00:00:00Z',
                'STATDES': 'Active',
                'UNI_DESC': 'Sample Contract'
            }
        ]
    }

    # Mock Priority customers
    priority_customers = [
        {
            'CUSTNAME': 'CUST001',
            'CUSTDES': 'Customer One',
            'STATDES': 'פעיל'  # Active in Hebrew
        }
    ]

    # Atera customers (matching Priority customer)
    atera_customers = {
        'items': [
            {
                'CustomerID': 999,
                'CustomerName': 'Customer One',
                'PriorityCustomerNumber': 'CUST001'
            }
        ]
    }

    # Atera contracts for this customer -> empty
    atera_contracts_empty = {
        'items': [],
        'page': 1,
        'itemsInPage': 0,
        'totalPages': 1
    }

    # Mock fetch Priority contracts
    mock_get_priority_contracts = mocker.patch('main.get_priority_contracts')
    mock_get_priority_contracts.return_value = priority_contracts['value']

    # Mock fetch Priority customers
    mock_get_priority_customers = mocker.patch('main.get_priority_customers')
    mock_get_priority_customers.return_value = priority_customers

    # Mock get Atera customers
    mock_get_atera_customers = mocker.patch('main.get_atera_customers')
    mock_get_atera_customers.return_value = atera_customers['items']

    # Mock get Atera contracts for a customer (no existing contracts)
    mock_get_atera_contracts_for_customer = mocker.patch('main.get_atera_contracts_for_customer')
    mock_get_atera_contracts_for_customer.return_value = atera_contracts_empty['items']

    # Mock create contract
    mock_create_atera_contract = mocker.patch('main.create_atera_contract')

    # Run
    sync_contracts()

    # Assert we tried to create it
    mock_create_atera_contract.assert_called_once()
    args, kwargs = mock_create_atera_contract.call_args
    customer_id_arg, contract_arg = args
    assert customer_id_arg == 999
    assert contract_arg['DOCNO'] == 'CONTRACT001'
    print("test_sync_contracts_create_new passed.")

def test_sync_contracts_skip_existing(mocker):
    """
    Test that if the contract's DOCNO already exists in Atera (via custom field),
    we skip creating a new one.
    """
    # Mock Priority API URL
    mocker.patch('main.PRIORITY_API_URL', 'http://test-priority-api')

    # Priority contracts (one contract) - updated recently
    priority_contracts = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'DOCNO': 'CONTRACT001',
                'UDATE': datetime.utcnow().isoformat() + 'Z',  # updated now
                'VALIDDATE': '2025-02-01T00:00:00Z',
                'EXPIRYDATE': '2025-12-31T00:00:00Z',
                'STATDES': 'Active',
                'UNI_DESC': 'Sample Contract'
            }
        ]
    }

    # Mock Priority customers
    priority_customers = [
        {
            'CUSTNAME': 'CUST001',
            'CUSTDES': 'Customer One',
            'STATDES': 'פעיל'  # Active in Hebrew
        }
    ]

    # Atera customers
    atera_customers = {
        'items': [
            {
                'CustomerID': 999,
                'CustomerName': 'Customer One',
                'PriorityCustomerNumber': 'CUST001'
            }
        ]
    }

    # Atera already has a contract with the same DOCNO in its custom field
    atera_contracts_with_one = {
        'items': [
            {
                "ContractID": 1234,
                "ContractName": "Sample Contract",
            }
        ],
        'page': 1,
        'itemsInPage': 1,
        'totalPages': 1
    }

    # Mock fetch Priority contracts
    mock_get_priority_contracts = mocker.patch('main.get_priority_contracts')
    mock_get_priority_contracts.return_value = priority_contracts['value']

    # Mock fetch Priority customers
    mock_get_priority_customers = mocker.patch('main.get_priority_customers')
    mock_get_priority_customers.return_value = priority_customers

    # Mock get Atera customers
    mock_get_atera_customers = mocker.patch('main.get_atera_customers')
    mock_get_atera_customers.return_value = atera_customers['items']

    # Mock get Atera contracts
    mock_get_atera_contracts_for_customer = mocker.patch('main.get_atera_contracts_for_customer')
    mock_get_atera_contracts_for_customer.return_value = atera_contracts_with_one['items']

    # Mock contract custom field fetch to return 'CONTRACT001' => means already exists
    def mock_get_atera_contract_custom_field_side_effect(contract_id, field_name):
        if contract_id == 1234 and field_name == 'Priority Contract Number':
            return 'CONTRACT001'
        return None

    mock_get_atera_contract_custom_field = mocker.patch(
        'main.get_atera_contract_custom_field',
        side_effect=mock_get_atera_contract_custom_field_side_effect
    )

    mock_create_atera_contract = mocker.patch('main.create_atera_contract')

    # Run
    sync_contracts()

    # Assert we did NOT create a new contract (skip logic)
    mock_create_atera_contract.assert_not_called()
    print("test_sync_contracts_skip_existing passed.")

@pytest.fixture
def priority_customer_fixture(request):
    """Returns a mock Priority customer object based on param."""
    # request.param = 'active' or 'inactive'
    return {
        'CUSTNAME': 'T003283',
        'CUSTDES': 'Customer One',
        'STATDES': 'פעיל' if request.param == 'active' else 'לא פעיל'
    }

@pytest.fixture
def priority_contract_fixture(request):
    """Returns a mock Priority contract object based on param."""
    # request.param = 'active' or 'inactive'
    return {
        'CUSTNAME': 'T003283',
        'CUSTDES': 'Customer One',
        'DOCNO': 'CONTRACT001',
        'UDATE': '2025-02-01T00:00:00Z',
        'VALIDDATE': '2025-02-01T00:00:00Z',
        'EXPIRYDATE': '2025-12-31T00:00:00Z',
        'STATDES': 'מבוטל' if request.param == 'inactive' else 'Active',
        'UNI_DESC': 'Sample Contract'
    }

@pytest.mark.parametrize("priority_customer_fixture", ["active", "inactive"], indirect=True)
@pytest.mark.parametrize("priority_contract_fixture", ["active", "inactive"], indirect=True)
def test_sync_contracts(
        priority_customer_fixture,
        priority_contract_fixture
):
    """
    4 combos:
     1) Active cust + Active contract => expect create
     2) Active cust + Inactive contract => skip
     3) Inactive cust + Active contract => skip
     4) Inactive cust + Inactive contract => skip
    """

    # Setup Mocks
    with patch("main.get_priority_customers") as mock_get_customers, \
            patch("main.get_priority_contracts") as mock_get_contracts, \
            patch("main.get_atera_customers") as mock_get_atera_customers, \
            patch("main.create_atera_contract") as mock_create_atera_contract, \
            patch("main.get_atera_contracts_for_customer", return_value=[]):

        # Mock returned data
        mock_get_customers.return_value = [priority_customer_fixture]
        mock_get_contracts.return_value = [priority_contract_fixture]
        mock_get_atera_customers.return_value = [{
            'CustomerID': 1234,
            'PriorityCustomerNumber': 'T003283'
        }]

        # Run the sync
        sync_contracts()

        customer_status = priority_customer_fixture['STATDES']
        contract_status = priority_contract_fixture['STATDES']

        # Only if customer_status == "פעיל" AND contract_status != "מבוטל" => create
        if customer_status == 'פעיל' and contract_status != 'מבוטל':
            mock_create_atera_contract.assert_called_once()
        else:
            mock_create_atera_contract.assert_not_called()

def test_sync_customers_filtered_by_date(mocker):
    """
    Test that only customers with MARH_UDATE in the last CUSTOMERS_PULL_PERIOD_DAYS
    are returned and processed by sync_customers().
    """
    # Suppose CUSTOMERS_PULL_PERIOD_DAYS=2
    cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=2)

    # We'll create two customers: one updated recently, one too old
    recent_update = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
    old_update = (datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=10)).isoformat()

    priority_customers_response = {
        'totalPages': 1,
        'value': [
            {
                'CUSTNAME': 'RECENT001',
                'CUSTDES': 'Recent Customer',
                'MARH_UDATE': recent_update,
                'PHONE': '111-222-3333',
                'ADDRESS': '123 Main St',
            },
            {
                'CUSTNAME': 'OLD001',
                'CUSTDES': 'Old Customer',
                'MARH_UDATE': old_update,
                'PHONE': '999-888-7777',
                'ADDRESS': '999 Old Rd',
            }
        ]
    }

    # Atera has no customers yet
    atera_customers_response = {
        'totalPages': 1,
        'totalItemCount': 0,
        'itemsInPage': 0,
        'items': []
    }

    # Mock GET calls
    def mock_get_side_effect(url, *args, **kwargs):
        if 'CUSTOMERS' in url:
            # Return both customers from Priority
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = priority_customers_response
            return response
        elif 'app.atera.com/api/v3/customers' in url and 'customerfield' not in url:
            response = mocker.MagicMock()
            response.status_code = 200
            response.json.return_value = atera_customers_response
            return response
        elif 'customerfield' in url:
            # Custom field doesn't exist
            response = mocker.MagicMock()
            response.status_code = 404
            return response
        else:
            raise ValueError(f"Unhandled URL in test: {url}")

    mocker.patch('main.requests.get', side_effect=mock_get_side_effect)
    mock_post = mocker.patch('main.requests.post')
    mock_put = mocker.patch('main.requests.put')
    mock_post.return_value = mocker.MagicMock(status_code=201, json=lambda: {'ActionID': 123})
    mock_put.return_value = mocker.MagicMock(status_code=200)

    # Run sync_customers
    sync_customers()

    # We should see creation for only the recent customer, not the old one
    create_calls = [
        call for call in mock_post.call_args_list
        if call.args[0] == "https://app.atera.com/api/v3/customers"
    ]
    assert len(create_calls) == 1, "Expected to create only 1 new customer (the recent one)."

    # Check that the created one is 'Recent Customer'
    data = create_calls[0].kwargs['json']
    assert data['CustomerName'] == 'Recent Customer'
    print("test_sync_customers_filtered_by_date passed.")
