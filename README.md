# ms

A website creator which is used for restaurant onwer. The website creator will create a website for the restaurant owner which help them upload their menus and manage their customer.

# ms_api

_Python server contains endpoints that is serving for MTYD website and MTYD mobile. Each endpoint will require specific format which the front end should follow in order to get the right response back._
_To run the server in local machine, please make sure to install all dependencies which are listed in **requirement.txt** and also we should run it on python virtual environment (after running virtual environment, run **pip3 install -r requirements.txt** to install all dependencies automatically.)_

_The server is hold at: **https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev.** and is updated through **zappa update dev** command (when running on local machine, the lambda's address above will be replaced by **localhost:2000**). Endpoints and its required format are listed as following:_

**--> SignUp: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/signup**

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

_--> Example JSON object for Sign up by social media (example object is using GOOGLE)<--_

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

**--> Login: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/login**

- The "Login" endpoint accepts only POST request with at least 2 parameters in its body. The first param is "email" and the second one is either "password" or "refresh_token". We are gonna re-use the token we got from facebook or google for our site and we'll pick the refresh token because it will not expire. For Apple token, we will use our token which is created by using user's email jwt encoded.

  _--> Example JSON object for Login by email:<--_

  {
  "email":"example@gmail.com",
  "password":"64a7f1fb0df93d8f5b9df14077948afa1b75b4c5028d58326fb801d825c9cd24412f88c8b121c50ad5c62073c75d69f14557255da1a21e24b9183bc584efef71"
  }

  **Note: password should be encoded before sending it to back end.**
  _--> Example JSON object for Login by social:<--_

  {
  "email":"example@gmail.com",
  "token": "this is a secret token"
  }

**AppleLogin, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/api/v2/apple\_login**

- This endpoint is used by Apple to redirect after authorizing. It accepts POST request with content type as a form-urlencoded which is sent by Apple.

**Change_Password, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/api/v2/change\_password**

- This endpoint is used for changing user's password. It accepts only POST request which requires the body of the request be formated as follow:

  {
  "customer_uid":"100-000001",
  "old_password":"old",
  "new_password":"new"
  }

**Reset_Password, https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/reset\_password**

- This endpoint is used for reset user's password in case they forgot their password. It accepts only GET request which requires a parameter named "email". So, the endpoint will send an email to the user which contains a temporary password for them to reset their password.

  _Example GET request: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev/api/v2/reset\_password?email=example@gmail.com_
