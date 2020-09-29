from ms_api import app
from env_keys import BING_API_KEY, RDS_PW
import pymysql
import requests
import unittest
import requests


RDS_HOST = 'io-mysqldb8.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
RDS_PORT = 3306
RDS_USER = 'admin'
RDS_DB = 'sf'
def connect():
    global RDS_PW
    global RDS_HOST
    global RDS_PORT
    global RDS_USER
    global RDS_DB

    print("Trying to connect to RDS (API v2)...")
    try:
        conn = pymysql.connect(RDS_HOST,
                               user=RDS_USER,
                               port=RDS_PORT,
                               passwd=RDS_PW,
                               db=RDS_DB,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
        print("Successfully connected to RDS. (API v2)")
        return conn
    except:
        print("Could not connect to RDS. (API v2)")
        raise Exception("RDS Connection failed. (API v2)")


# Disconnect from MySQL database (API v2)
def disconnect(conn):
    try:
        conn.close()
        print("Successfully disconnected from MySQL database. (API v2)")
    except:
        print("Could not properly disconnect from MySQL database. (API v2)")
        raise Exception("Failure disconnecting from MySQL database. (API v2)")

def execute(sql, cmd, conn, skipSerialization=False):
    response = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cmd == 'get':
                result = cur.fetchall()
                response['message'] = 'Successfully executed SQL query.'
                # Return status code of 280 for successful GET request
                response['code'] = 280
                if not skipSerialization:
                    result = serializeResponse(result)
                response['result'] = result
            elif cmd == 'post':
                conn.commit()
                response['message'] = 'Successfully committed SQL command.'
                # Return status code of 281 for successful POST request
                response['code'] = 281
            else:
                response['message'] = 'Request failed. Unknown or ambiguous instruction given for MySQL command.'
                # Return status code of 480 for unknown HTTP method
                response['code'] = 480
    except:
        response['message'] = 'Request failed, could not execute MySQL command.'
        # Return status code of 490 for unsuccessful HTTP request
        response['code'] = 490
    finally:
        return response

class FlaskTestCases(unittest.TestCase):
    def test_get_client(self):
        endpoints = [
            '/api/v2/customer_lplp?customer_uid=100-000001',
            '/api/v2/meals_selected?customer_uid=100-000001',
            '/api/v2/accountsalt?email=quang@gmail.com',
            '/api/v2/next_addon_charge?purchase_uid=400-000001',
            '/api/v2/upcoming_menu'
        ]
        for e in endpoints:
            with self.subTest(name=e):
                tester = app.test_client()
                response = tester.get(e)
                self.assertEqual(response.status_code, 200)

    def test_get_admin(self):
        endpoints = [
            '/api/v2/get_menu',
            '/api/v2/get_orders_by_purchase_id?business_uid=200-000001',
            '/api/v2/plans?business_uid=200-000007',
            '/api/v2/ingredients',
            '/api/v2/get_ingredients_to_purchase?business_uid=200-000001',
            '/api/v2/get_meals',
            '/api/v2/recipes',
            '/api/v2/coupons',
            '/api/v2/get_orders_by_menu_date?business_uid=200-000001',
            '/api/v2/measure_unit',
        ]
        for e in endpoints:
            with self.subTest(name=e):
                tester = app.test_client()
                response = tester.get(e)
                self.assertEqual(response.status_code, 200)

    def test_login(self):
        payload = {
            "email": "quang@gmail.com",
            "password": "cec35d4fc0c5e83527f462aeff579b0c6f098e45b01c8b82e311f87dc6361d752c30293e27027653adbb251dff5d03242c8bec68a3af1abd4e91c5adb799a01b"
        }
        tester = app.test_client()
        response = tester.post('http://localhost:2000/api/v2/login', json=payload)
        self.assertEqual(response.status_code, 200)

    def test_post_signup_by_email(self):
        payload = {
                "email": "example@gmail.com",
                "password": "1",
                "first_name": "Clark",
                "last_name": "Kent",
                "address": "Everywhere",
                "unit": "",
                "city": "Krypton",
                "state": "Space",
                "zip_code": "12345",
                "latitude": 123456,
                "longitude": 12.2154,
                "phone_number": "5105846166",
                "referral_source": "Website",
                "role": "customer",
                "social": False
        }
        tester = app.test_client()
        response = tester.post("http://localhost:2000/api/v2/signup", json=payload)
        if response.status_code == 201:
            conn = connect()
            id = response.get_json(force=True)['result']['customer_uid']
            res = execute("DELETE FROM customers WHERE customer_uid= '" + id + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in CUSTOMER table manually. customer_uid = '" + id + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
        self.assertEqual(response.status_code, 201)
    def test_post_signup_by_social(self):
        payload = {
            "email": "example@gmail.com",
            "access_token": "this is a access_token",
            "refresh_token": "this is a secret refresh_token",
            "first_name": "Lex",
            "last_name": "Luther",
            "address": "Somewhere on Earth",
            "unit": "",
            "city": "Rich",
            "state": "Millionaire",
            "zip_code": "94578",
            "latitude": 123456,
            "longitude": 12.2154,
            "phone_number": "1234567890",
            "referral_source": "Friends",
            "role": "boss",
            "social": "Twitter"
        }
        tester = app.test_client()
        response = tester.post("http://localhost:2000/api/v2/signup", json=payload)
        if response.status_code == 201:
            conn = connect()
            id = response.get_json(force=True)['result']['customer_uid']
            res = execute("DELETE FROM customers WHERE customer_uid= '" + id + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in CUSTOMER table manually. customer_uid = '" + id + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
        self.assertEqual(response.status_code, 201)
    def test_post_checkout(self):
        payload = {
                    "customer_uid": "100-000082",
                    "business_uid": "200-000001",
                    "items": [{"qty": "5", "name": "Collards (bunch)", "price": "2.5", "item_uid": "320-000009", "pur_business_uid": "200-000001", "delivery_date": "2020-08-30 12:00:00"}],
                    "salt": "64a7f1fb0df93d8f5b9df14077948afa1b75b4c5028d58326fb801d825c9cd24412f88c8b121c50ad5c62073c75d69f14557255da1a21e24b9183bc584efef71",
                    "delivery_first_name": "Quang",
                    "delivery_last_name": "Dang",
                    "delivery_email": "vinhquangdang1@gmail.com",
                    "delivery_phone": "5105846166",
                    "delivery_address": "1320 144th Ave",
                    "delivery_unit": "",
                    "delivery_city": "San Leandro",
                    "delivery_state": "CA",
                    "delivery_zip": "94578",
                    "delivery_instructions": "Nothing",
                    "delivery_longitude": "0.23243445",
                    "delivery_latitude": "-121.332",
                    "order_instructions": "Nothing",
                    "purchase_notes": "testing",
                    "amount_due": "300.00",
                    "amount_discount": "0.00",
                    "amount_paid": "0.00",
                    "cc_num": "4242424242424242",
                    "cc_exp_year": "2022",
                    "cc_exp_month": "08",
                    "cc_cvv": "123",
                    "cc_zip": "12345"
                }
        tester = app.test_client()
        response = tester.post("http://localhost:2000/api/v2/checkout", json=payload)
        if response.status_code == 201:
            conn = connect()
            data = response.get_json(force=True)
            purchase_id = data['purchase_id']
            payment_id = data['payment_id']
            res = execute("DELETE FROM purchases WHERE purchase_uid= '" + purchase_id + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in PURCHASES table manually. purchase_uid = '" + purchase_id + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
            res = execute("DELETE FROM payments WHERE payment_uid= '" + payment_id + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in PAYMENTS table manually. payment_uid = '" + payment_id + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
        self.assertEqual(response.status_code, 201)

    def test_post_addon_selection(self):
        payload = {
                    "is_addon": true,
                    "items":[{"qty": "5", "name": "Collards (bunch)", "price": "2.5", "item_uid": "310-000022"}, {"qty": "6", "name": "Broccoli (bunch)", "price": "3.5", "item_uid": "310-000023"}],
                    "purchase_id": "400-000024",
                    "menu_date":"2020-08-09",
                    "delivery_day": "Sunday"
                }
        tester = app.test_client()
        response = tester.post("http://localhost:2000/api/v2/meals_selection", json=payload)
        if response.status_code == 201:
            conn = connect()
            data = response.get_json(force=True)
            selection_uid = data['selection_uid']
            res = execute("DELETE FROM addons_selected WHERE selection_uid= '" + selection_uid + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in ADDONS_SELECTED table manually. Selection_uid = '" + selection_uid + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
        self.assertEqual(response.status_code, 201)

    def test_post_meal_selection(self):
        payload = {
                    "is_addon": False,
                    "items":[{"qty": "", "name": "SKIP", "price": "", "item_uid": "320-000002"}],
                    "purchase_id": "400-000024",
                    "menu_date":"2020-08-09",
                    "delivery_day": "SKIP"
                }
        tester = app.test_client()
        response = tester.post("http://localhost:2000/api/v2/meals_selection", json=payload)
        if response.status_code == 201:
            conn = connect()
            data = response.get_json(force=True)
            selection_uid = data['selection_uid']
            res = execute("DELETE FROM addons_selected WHERE selection_uid= '" + selection_uid + "';", 'post', conn)
            if res['code'] != 281:
                string = " Need to delete a new record in MEALS_SELECTED table manually. Selection_uid = '" + selection_uid + "'"
                print("\n")
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                print("\n")
        self.assertEqual(response.status_code, 201)
if __name__ == "__main__":
    unittest.main()
