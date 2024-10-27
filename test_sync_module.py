# test_sync_module.py

import pytest
from main import sync_customers, sync_contacts

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
                'ZIP': '90001'
            }
        ]
    }

    atera_customer = {
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
        headers=mocker.ANY,
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
        headers=mocker.ANY,
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
                'ZIP': '90001'
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
        headers=mocker.ANY,
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
    # Define test data
    priority_contacts = {
        'value': [
            {
                'CUSTNAME': 'CUST001',
                'CUSTDES': 'Customer One',
                'EMAIL': '',  # Missing email
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
                'FIRSTNAME': '',  # Missing both names
                'LASTNAME': '',
                'POSITIONDES': 'Technician',
                'PHONENUM': '',
                'CELLPHONE': ''
            }
        ]
    }

    atera_customers = {
        'items': [
            {
                'CustomerID': 1,
                'CustomerName': 'Customer One',
                'PriorityCustomerNumber': 'CUST001',
            }
        ]
    }

    atera_contacts = {
        'items': []
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
            # Return a response indicating that the custom field is not found
            response = mocker.MagicMock()
            response.status_code = 404
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
    assert data_smith['Firstname'] == ''  # First name missing
    assert data_smith['Lastname'] == 'Smith'
    assert data_smith['Email'] == 'bob@example.com'  # Provided email

    print("Contacts sync test passed.")
