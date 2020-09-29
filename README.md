# ms

A website creator which is used for restaurant onwer. The website creator will create a website for the restaurant owner which help them upload their menus and manage their customer.

# ms_api

_Python server contains endpoints that is serving for MTYD website and MTYD mobile. Each endpoint will require specific format which the front end should follow in order to get the right response back._
_To run the server in local machine, please make sure to install all dependencies which are listed in **requirement.txt** and also we should run it on python virtual environment (after running virtual environment, run **pip3 install -r requirements.txt** to install all dependencies automatically.)_

*The server is hold at: **https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev.** and is updated through **zappa update dev** command (when running on local machine, the lambda's address above will be replaced by **localhost:2000**). Endpoints and its required format are listed as following:*

**>>> SignUp: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/signup**

  - The "signup" endpoint accepts only POST request with body contains a required JSON object as following:

   _--> Example JSON object for Sign up by email: <--_

    {
      "email":"example@gmail.com",
      "password":"super_secret",
      "first_name":"Iron",
      "last_name": "Man",
      "address":"Some where on Earth",
      "unit":"Some where on Earth",
      "city":"Some where on Earth",
      "state": "Some where on Earth",
      "zip_code": "12345",
      "latitude": 123456,
      "longitude": 12.2154,
      "phone_number": "1234567890",
      "referral_source":"Website",
      "role":"user's role",
      "social": false
    }

   *--> Example JSON object for Sign up by social media (example object is using GOOGLE)<--*
    
    {
      "email":
      "example@gmail.com",
      "access_token": "this is a access_token",
      "refresh_token": "this is a secret refresh_token",
      "first_name": "Hulk",
      "last_name": "Green",
      "address": "Some where on Earth",
      "unit": "Some where on Earth",
      "city": "Some where on Earth",
      "state": "Some where on Earth",
      "zip_code": "12345",
      "latitude": 123456,
      "longitude": 12.2154,
      "phone_number": "1234567890",
      "referral_source": "Website",
      "role": "user's role",
      "social": "GOOGLE"
    }

**>>> Login: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/login**

- The "Login" endpoint accepts only POST request with at least 2 parameters in its body. The first param is "email" and the second one is either "password" or "refresh_token". We are gonna re-use the token we got from facebook or google for our site and we'll pick the refresh token because it will not expire. For Apple token, we will use our token which is created by using user's email jwt encoded.

  _--> Example JSON object for Login by email:<--_

  ```
  {
    "email":"example@gmail.com",
    "password":"64a7f1fb0df93d8f5b9df14077948afa1b75b4c5028d58326fb801d825c9cd24412f88c8b121c50ad5c62073c75d69f14557255da1a21e24b9183bc584efef71"
  }
  ```

  > **Notice:** password should be encoded before sending it to back end.

  _--> Example JSON object for Login by social:<--_

  ```
  {
    "email":"example@gmail.com",
    "token": "this is a secret token"
  }
  ```

**>>> AppleLogin, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/api/v2/apple_login**

- This endpoint is used by Apple to redirect after authorizing. It accepts POST request with content type as a form-urlencoded which is sent by Apple.

**>>> Change_Password, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/api/v2/change_password**

- This endpoint is used for changing user's password. It accepts only POST request which requires the body of the request be formated as follow:

  ```
  {
    "customer_uid":"100-000001",
    "old_password":"old",
    "new_password":"new"
  }
  ```

**>>> Reset_Password, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/reset_password**

- This endpoint is used for reset user's password in case they forgot their password. It accepts only GET request which requires a parameter named "email". So, the endpoint will send an email to the user which contains a temporary password for them to reset their password.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/reset_password?email=example@gmail.com*

**>>> Meals_Selected, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/meals_selected**

- The "Meals_Selected" only accepts GET request with one required parameters "customer_id".It will return the information of all selected meals and addons which are associated with the specific purchase.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2//api/v2/meals_selected?customer_uid=100-000001*

**>>> Get_Upcoming_Menu, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/upcoming_menu**

- The "Get_Upcoming_Menu" only accepts GET request without required param. It will return the information of all upcoming menu items.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/upcoming_menu*

**>>> Get_Latest_Purchases_Payments, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/customer_lplp**

- The "Get_Latest_Purchases_Payments" only accepts GET request with 1 required parameters "customer_uid". It will return the information of all current purchases of the customer associated with the given customer_uid.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/customer_lplp?customer_uid=100-000001*

**>>> Next_Billing_Date, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/next_billing_date**

- The "next_Billing_Date" only accepts GET request with parameter named "customer_uid". It will return the next billing charge information.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/next_billing_date?customer_uid=100-000001*

**>>> Next_Addon_Charge, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/next_addon_charge**

- The "next_addon_charge" only accepts GET request with required parameter named "purchase_uid". It will return the next addon charge information.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/next_addon_charge?purchase_uid=400-000001*

**>>> AccountSalt, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/accountsalt**

- The "accountsalt" endpoint accepts only GET request with one required parameter.It will return the information of password hashed and password salt for an associated email account.

  *Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/accountsalt?email=quang@gmail.com*

**>>> Checkout, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/checkout**

- The "checkout" accepts POST request with appropriate parameters. The JSON object format is shown below:

  ```
  {
    "customer_uid":"100-000082",
    "business_uid": "200-000001",
    "items": [{"qty": "5", "name": "Collards (bunch)", "price": "2.5", "item_uid":"320-000009", "pur_business_uid":"200-000001", "delivery_date":"2020-08-30 12:00:00"}],
    "salt": "64a7f1fb0df93d8f5b9df14077948afa1b75b4c5028d58326fb801d825c9cd24412f88c8b121c50ad5c62073c75d69f14557255da1a21e24b9183bc584efef71",
    "delivery_first_name":"Captain",
    "delivery_last_name":"American",
    "delivery_email":"avenger@gmail.com",
    "delivery_phone":"1234567890",
    "delivery_address":"Shield",
    "delivery_unit":"",
    "delivery_city":"Hollywood",
    "delivery_state":"CA",
    "delivery_zip":"12345",
    "delivery_instructions":"Carefull with Hulk",
    "delivery_longitude":"0.23243445",
    "delivery_latitude":"-121.332",
    "order_instructions":"Nothing",
    "purchase_notes":"testing",
    "amount_due":"300.00",
    "amount_discount":"0.00",
    "amount_paid":"0.00",
    "cc_num": "4242424242424242",
    "cc_exp_year": "2022",
    "cc_exp_month": "08",
    "cc_cvv":"123",
    "cc_zip":"12345"
  }
  ```

> **Notice**: For testing purpose, we have to use testing credit card which is listed on [stripe's website](https://stripe.com/docs/testing)

**>>> Meals_Selection, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/meals_selection'**

- The "Meals_Selection" accepts POST request with appropriate parameters. The JSON object format is shown below:

  _-->Example for meal selection:<--_

  ```
  {
    "is_addon": false,
    "items":[{"qty": "", "name": "SKIP", "price": "", "item_uid": "320-000002"}],
    "purchase_id": "400-000024",
    "menu_date":"2020-08-09",
    "delivery_day": "SKIP"
  }
  ```

  _--> Example for add on selection: <--_

  ```
  {
    "is_addon": true,
    "items":[{"qty": "5", "name": "Collards (bunch)", "price": "2.5", "item_uid": "310-000022"}, {"qty": "6", "name": "Broccoli (bunch)", "price": "3.5", "item_uid": "310-000023"}],
    "purchase_id": "400-000024",
    "menu_date":"2020-08-09",
    "delivery_day": "Sunday"
  }
  ```

> **Notice:** if is_addon: true means that we are selecting for add on, so the sending data will be written into the addon_selected table and if is_addon: false then the sending data will be written into the meals_selected table.

**There are still some endpoints have not completed yet. We will update this README when we have those endpoints tested.**

# ms_api_test

_This is a automatic test for ms_api.py. In order to run this test, the "ms_api.py" must be run at local machine. This test was written by using Python unit test._
