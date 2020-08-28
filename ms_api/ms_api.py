from flask import Flask, request, render_template, url_for, redirect
from flask_restful import Resource, Api
from flask_mail import Mail, Message  # used for email
# used for serializer email and error handling
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from flask_cors import CORS

from werkzeug.exceptions import BadRequest, NotFound

from dateutil.relativedelta import *
from decimal import Decimal
from datetime import datetime, date, timedelta
from hashlib import sha512
from math import ceil
import string
import random

from env_keys import BING_API_KEY, RDS_PW

import decimal
import sys
import json
import pytz
import pymysql
import requests
import stripe
import binascii
stripe_public_key = 'pk_test_6RSoSd9tJgB2fN2hGkEDHCXp00MQdrK3Tw'
stripe_secret_key = 'sk_test_fe99fW2owhFEGTACgW3qaykd006gHUwj1j'
stripe.api_key = stripe_secret_key
# RDS for AWS SQL 5.7
# RDS_HOST = 'pm-mysqldb.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
# RDS for AWS SQL 8.0
RDS_HOST = 'io-mysqldb8.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
RDS_PORT = 3306
RDS_USER = 'admin'
RDS_DB = 'sf'

app = Flask(__name__)
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
# Set this to false when deploying to live application
app.config['DEBUG'] = True
# Adding for email testing
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'ptydtesting@gmail.com'
app.config['MAIL_PASSWORD'] = 'ptydtesting06282020'
app.config['MAIL_DEFAULT_SENDER'] = 'ptydtesting@gmail.com'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
# app.config['MAIL_DEBUG'] = True
# app.config['MAIL_SUPPRESS_SEND'] = False
# app.config['TESTING'] = False

mail = Mail(app)
s = URLSafeTimedSerializer('thisisaverysecretkey')
# API
api = Api(app)

# convert to UTC time zone when testing in local time zone
utc = pytz.utc
def getToday(): return datetime.strftime(datetime.now(utc), "%Y-%m-%d")
def getNow(): return datetime.strftime(datetime.now(utc),"%Y-%m-%d %H:%M:%S")

# Connect to MySQL database (API v2)
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
                               use_unicode=True,
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


# Serialize JSON
def serializeResponse(response):
    try:
        for row in response:
            for key in row:
                if type(row[key]) is Decimal:
                    row[key] = float(row[key])
                elif isinstance(row[key], bytes):
                    row[key] = row[key].decode()
                elif (type(row[key]) is date or type(row[key]) is datetime) and row[key] is not None:
                    row[key] = row[key].strftime("%Y-%m-%d")
        return response
    except:
        raise Exception("Bad query JSON")


# Execute an SQL command (API v2)
# Set cmd parameter to 'get' or 'post'
# Set conn parameter to connection object
# OPTIONAL: Set skipSerialization to True to skip default JSON response serialization
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
        # response['sql'] = sql
        return response

def get_new_paymentID(conn):
    newPaymentQuery = execute("CALL new_payment_uid", 'get', conn)
    if newPaymentQuery['code'] == 280:
        return newPaymentQuery['result'][0]['new_id']
    return "Could not generate new payment ID", 500



def get_new_purchaseID(conn):
    newPurchaseQuery = execute("CALL new_purchase_uid", 'get', conn)
    if newPurchaseQuery['code'] == 280:
        return newPurchaseQuery['result'][0]['new_id']
    return "Could not generate new purchase ID", 500

def simple_get_execute(query, name_to_show, conn):
    response = {}
    res = execute(query, 'get', conn)
    if res['code'] != 280:
        string = " Cannot run the query for " + name_to_show + ". "
        print("*" * (len(string) + 10))
        print(string.center(len(string) + 10, "*"))
        print("*" * (len(string) + 10))
        response['message'] = 'Internal Server Error.'
        return response, 500
    elif not res['result']:
        response['message'] = 'Not Found'
        return response, 404
    else:
        response['message'] = "Get " + name_to_show + " successful."
        response['result'] = res['result']

        return response, 200

class SignUp(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            should_delete = False
            data = request.get_json(force=True)

            email = data['email']
            firstName = data['first_name']
            lastName = data['last_name']
            phone = data['phone_number']
            address = data['address']
            unit = "'" + data['unit'] + "'" if data.get('unit') is not None else 'NULL'
            city = data['city']
            state = data['state']
            zip_code = data['zip_code']
            latitude = data['latitude']
            longitude = data['longitude']

            referral = data['referral_source']
            role = data['role']
            if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False:
                social_signup = False
            else:
                social_signup = True


            # check if there is a same customer_id existing
            query = """
                    SELECT customer_email FROM customers
                    WHERE customer_email = \'""" + email + "\';"

            emailExists = execute(query, 'get', conn)
            if emailExists['code'] != 280:
                string = " Cannot run the query for " + __class__.__name__ + ". "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = 'Internal Server Error.'
                return response, 500
            elif emailExists['code'] == 280 and len(emailExists['result']) > 0:
                response['message'] = 'Email address is already taken.'
                return response, 409

            get_user_id_query = "CALL new_customer_uid();"
            NewUserIDresponse = execute(get_user_id_query, 'get', conn)

            if NewUserIDresponse['code'] == 490:
                string = " Cannot get new User id. "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = "Internal Server Error."
                return response, 500
            NewUserID = NewUserIDresponse['result'][0]['new_id']

            if social_signup == False:
                salt = getNow()
                password = "'" + sha512((data['password'] + salt).encode()).hexdigest() + "'"
                algorithm = "'SHA512'"
                salt = "'" + salt + "'"
                access_token = 'NULL'
                refresh_token = 'NULL'
                user_social_signup = 'NULL'
            else:
                access_token = data['access_token']
                refresh_token = data['refresh_token']
                salt = 'NULL'
                password = 'NULL'
                algorithm = 'NULL'
                user_social_signup = "'" + data['social'] + "'"

            # write everything to database
            customer_insert_query = """
                                    INSERT INTO customers 
                                    (
                                        customer_uid,
                                        customer_created_at,
                                        customer_first_name,
                                        customer_last_name,
                                        customer_phone_num,
                                        customer_email,
                                        customer_address,
                                        customer_unit,
                                        customer_city,
                                        customer_state,
                                        customer_zip,
                                        customer_lat,
                                        customer_long,
                                        password_salt,
                                        password_hashed,
                                        password_algorithm,
                                        referral_source,
                                        role,
                                        user_social_media,
                                        user_access_token,
                                        user_refresh_token
                                    )
                                    VALUES
                                    (
                                        '""" + NewUserID + """',
                                        '""" + getNow() + """',
                                        '""" + str(firstName) + """',
                                        '""" + str(lastName) + """',
                                        '""" + str(phone) + """',
                                        '""" + str(email) + """',
                                        '""" + str(address) + """',
                                        """ + str(unit) + """,
                                        '""" + str(city) + """',
                                        '""" + str(state) + """',
                                        '""" + str(zip_code) + """',
                                        '""" + str(latitude) + """',
                                        '""" + str(longitude) + """',
                                        """ + str(salt) + """,
                                        """ + str(password) + """,
                                        """ + str(algorithm) + """,
                                        '""" + str(referral) + """',
                                        '""" + str(role) + """',
                                        """ + str(user_social_signup) + """,
                                        """ + str(access_token) + """,
                                        """ + str(refresh_token) + """
                                    );
                                    """
            usnInsert = execute(customer_insert_query, 'post', conn)
            if usnInsert['code'] != 281:
                string = " Cannot Insert into the customers table. "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = "Internal Server Error."
                return response, 500
            should_delete = True  # this is used for error handle
            # Sending verification email
            if social_signup == False:
                token = s.dumps(email)

                msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[email])

                link = url_for('confirm', token=token, hashed=password, _external=True)

                msg.body = "Click on the link {} to verify your email address.".format(link)

                mail.send(msg)
            result = {
                'first_name': firstName,
                'last_name': lastName,
                'customer_uid': NewUserID,
                'access_token': access_token,
                'refresh_token': refresh_token
            }
            response['message'] = "OK"
            response['result'] = result

            return response, 200
        except:
            print("Error happened while Sign Up")
            if should_delete:
                execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
# confirmation page
@app.route('/api/v2/confirm/<token>/<hashed>', methods=['GET'])
def confirm(token, hashed):
    try:
        email = s.loads(token)  # max_age = 86400 = 1 day
        # marking email confirmed in database, then...
        conn = connect()
        query = """UPDATE customers SET email_verified = 1 WHERE email = \'""" + email + """\';"""
        update = execute(query, 'post', conn)
        if update.get('code') == 281:
            # redirect to login page
            # return redirect('http://preptoyourdoor.netlify.app/login/{}/{}'.format(email, hashed))
            return redirect('http://localhost:3000/login/{}/{}'.format(email, hashed))
        else:
            print("Error happened while confirming an email address.")
            error = "Confirm error."
            err_code = 401  # Verification code is incorrect
            return error, err_code
    except (SignatureExpired, BadTimeSignature) as err:
        status = 403  # forbidden
        return str(err), status
    finally:
        disconnect(conn)

def LogLoginAttempt(data, conn):
    try:
        response = {}

        login_id_res = execute("CALL get_login_id;", 'get', conn)
        login_id = login_id_res['result'][0]['new_id']
        # Generate random session ID

        if data["auth_success"] == "TRUE":
            session_id = "\'" + sha512(getNow().encode()).hexdigest() + "\'"
        else:
            session_id = "NULL"
        sql = """
            INSERT INTO ptyd_login (
                login_attempt
                , login_password
                , login_user_uid
                , ip_address
                , ip_version
                , browser_type
                , attempt_datetime
                , successBool
                , session_id
            )
            VALUES
            (
                \'""" + login_id + """\'
                , \'""" + data["attempt_hash"] + """\'
                , \'""" + data["user_uid"] + """\'
                , \'""" + data["ip_address"] + """\'
                , \'""" + ipVersion(data["ip_address"]) + """\'
                , \'""" + data["browser_type"] + """\'
                , \'""" + getNow() + """\'
                , \'""" + data["auth_success"] + """\'
                , """ + session_id + """
            );
            """
        log = execute(sql, 'post', conn)

        if session_id != "NULL":
            session_id = session_id[1:-1]
            print(session_id)

        response['session_id'] = session_id
        response['login_id'] = login_id
        print(log)

        return response
    except:
        print("Could not log login attempt.")
        return None

class Login (Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            email = request.args['email']
            password = request.args.get('password')
            refresh_token = request.args.get('token')
            query = """
                    # CUSTOMER QUERY 1: LOGIN
                    SELECT customer_uid,
                            customer_last_name,
                            customer_first_name,
                            customer_email, 	
                            password_hashed, 	
                            password_salt,
                            email_verified, 	
                            user_social_media,
                            user_access_token,
                            user_refresh_token  
                    FROM sf.customers c 
                    -- WHERE customer_email = "1m4kfun@gmail.com";
                    WHERE customer_email = \'""" + email + """\';
                    """
            res = execute(query, 'get', conn)
            if res['code'] != 280:
                string = " Cannot run the query for " + __class__.__name__ + ". "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = 'Internal Server Error.'
                return response, 500
            elif not res['result']:
                response['message'] = 'Not Found'
                return response, 404
            else:
                if password is not None and res['result'][0]['user_social_media'] == 'TRUE':
                    response['message'] = "Need to login by Social Media"
                    return response, 401
                elif (password is None and refresh_token is None) or (password is None and res['result'][0]['user_social_media'] == 'FALSE'):
                    return BadRequest("Bad request.")
                # compare passwords if user_social_media is false
                elif (res['result'][0]['user_social_media'] == 'FALSE' or res['result'][0]['user_social_media']=="") and password is not None:
                    salt = res['result'][0]['password_salt']
                    hashed = sha512((password + salt).encode()).hexdigest()
                    if res['result'][0]['password_hashed'] != hashed:
                        response['message'] = "Wrong password."
                        return response, 401
                    if res['result'][0]['email_verified'] == 0 or res['result'][0]['email_verified'] == "FALSE":
                        response['message'] = "Account need to be verified by email."
                        return response, 401
                # compare the refresh token because it never expire.
                elif res['result'][0]['user_social_media'] == 'TRUE':
                    if res['result'][0]['user_refresh_token'] != refresh_token:
                        response['message'] = "Cannot Authenticated. Token is invalid."
                        return response, 401
                else:
                    string = " Cannot compare the password or refresh token while log in. "
                    print("*" * (len(string) + 10))
                    print(string.center(len(string) + 10, "*"))
                    print("*" * (len(string) + 10))
                    response['message'] = 'Internal Server Error.'
                    return response, 500
                del res['result'][0]['password_hashed']
                del res['result'][0]['password_salt']

                response['message'] = "Authenticated success."
                response['result'] = res['result'][0]
                return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class AccountSalt(Resource):
    def get(self):
        try:
            conn = connect()
            email = request.args['email']
            query = """
                    SELECT password_hashed, 
                            password_salt 
                    FROM customers cus
                    WHERE customer_email = \'""" + email + """\';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals(Resource):
    global RDS_PW

    # Format queried tuples into JSON
    def jsonifyMeals(self, query, mealKeys):
        json = {}
        for key in [('Weekly', 'WEEKLY SPECIALS'), ('Seasonal', 'SEASONAL FAVORITES'), ('Smoothies', 'SMOOTHIES')]:
            json[key[0]] = {'Category': key[1], 'Menu': []}
        decimalKeys = ['extra_meal_price', 'meal_calories', 'meal_protein',
                       'meal_carbs', 'meal_fiber', 'meal_sugar', 'meal_fat', 'meal_sat']
        indexOfMealId = mealKeys.index('menu_meal_id')
        for row in query:
            if row[indexOfMealId] is None:
                continue
            rowDict = {}
            for element in enumerate(row):
                key = mealKeys[element[0]]
                value = element[1]
                # Convert all decimal values in row to floats
                if key in decimalKeys:
                    value = float(value)
                if key == 'menu_date':
                    value = value.strftime("%Y-%m-%d")
                rowDict[key] = value
            # Hardcode quantity to 0
            # Will need to fetch from db eventually
            rowDict['quantity'] = 0
            #           rowDict['meal_photo_url'] = 'https://prep-to-your-door-s3.s3.us-west-1.amazonaws.com/dev_imgs/700-000014.png'
            if 'SEAS_FAVE' in rowDict['menu_category']:
                json['Seasonal']['Menu'].append(rowDict)
            elif 'WKLY_SPCL' in rowDict['menu_category']:
                json['Weekly']['Menu'].append(rowDict)
            elif rowDict['menu_category'] in ['ALMOND_BUTTER', 'THE_ENERGIZER', 'SEASONAL_SMOOTHIE', 'THE_ORIGINAL']:
                json['Smoothies']['Menu'].append(rowDict)
        return json

    def jsonifyAddons(self, query, mealKeys):
        json = {}
        for key in [('Addons', 'ADD-ON'), ('Weekly', 'ADD MORE MEALS'), ('Smoothies', 'ADD MORE SMOOTHIES')]:
            json[key[0]] = {'Category': key[1], 'Menu': []}
        decimalKeys = ['extra_meal_price', 'meal_calories', 'meal_protein',
                       'meal_carbs', 'meal_fiber', 'meal_sugar', 'meal_fat', 'meal_sat']
        indexOfMealId = mealKeys.index('menu_meal_id')
        for row in query:
            if row[indexOfMealId] is None:
                continue
            rowDict = {}
            for element in enumerate(row):
                key = mealKeys[element[0]]
                value = element[1]
                # Convert all decimal values in row to floats
                if key in decimalKeys:
                    value = float(value)
                if key == 'menu_date':
                    value = value.strftime("%Y-%m-%d")
                rowDict[key] = value
            # Hardcode quantity to 0
            # Will need to fetch from db eventually
            rowDict['quantity'] = 0
            # rowDict['meal_photo_url'] = 'https://prep-to-your-door-s3.s3.us-west-1.amazonaws.com/dev_imgs/700-000014.png'
            if rowDict['menu_category'] in ['ALMOND_BUTTER', 'THE_ENERGIZER', 'SEASONAL_SMOOTHIE', 'THE_ORIGINAL']:
                json['Smoothies']['Menu'].append(rowDict)
            elif 'SEAS_FAVE' in rowDict['menu_category']:
                json['Weekly']['Menu'].append(rowDict)
            elif 'WKLY_SPCL' in rowDict['menu_category']:
                json['Weekly']['Menu'].append(rowDict)
            else:
                json['Addons']['Menu'].append(rowDict)

        return json

    def getMealQuantities(self, menu):
        mealQuantities = {}
        for key in ['Meals', 'Addons']:
            for subMenu in menu[key]:
                for eachMeal in menu[key][subMenu]['Menu']:
                    meal_id = eachMeal['meal_id']
                    mealQuantities[meal_id] = 0
        return mealQuantities

    def getAddonPrice(self, menu):

        savedAddonPrice = {}
        for key in ['Meals', 'Addons']:
            for subMenu in menu[key]:
                for eachMeal in menu[key][subMenu]['Menu']:
                    related_price = eachMeal['meal_price']
                    meal_id = eachMeal['meal_id']
                    savedAddonPrice[meal_id] = related_price
        return savedAddonPrice

    # HTTP method GET
    # Optional parameter: startDate (YYYYMMDD)
    def get(self, startDate=None):
        response = {}
        items = {}

        try:
            if startDate:
                now = datetime.strptime(startDate, "%Y%m%d")
            else:
                now = datetime.now()

        except:
            raise BadRequest('Request failed, bad startDate parameter.')

        try:
            conn = connect()

            dates = execute(
                "SELECT DISTINCT menu_date FROM menu;", 'get', conn)
            i = 1

            for date in dates['result']:
                # only grab 6 weeks worth of menus
                if i == 7:
                    break
                # convert string to datetime
                stamp = datetime.strptime(date['menu_date'], '%Y-%m-%d')

                # Roll calendar at 4PM Monday
                if now - timedelta(days=1, hours=16) < stamp:
                    weekly_special = execute(
                        """
                        SELECT
                            meal_id,
                            meal_name,
                            menu_date,
                            menu_category,
                            menu_meal_id,
                            meal_desc,
                            meal_category,
                            meal_photo_url,
                            meal_price,
                            meal_calories,
                            meal_protein,
                            meal_carbs,
                            meal_fiber,
                            meal_sugar,
                            meal_fat,
                            meal_sat
                        FROM menu
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_id
                        WHERE (menu_category = 'WKLY_SPCL_1' OR menu_category = 'WKLY_SPCL_2' OR menu_category = 'WKLY_SPCL_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    print("weekly_special: ", weekly_special)
                    seasonal_special = execute(
                        """
                        SELECT
                            meal_id,
                            meal_name,
                            menu_date,
                            menu_category,
                            menu_meal_id,
                            meal_desc,
                            meal_category,
                            meal_photo_url,
                            meal_price,
                            meal_calories,
                            meal_protein,
                            meal_carbs,
                            meal_fiber,
                            meal_sugar,
                            meal_fat,
                            meal_sat
                        FROM menu
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_id
                        WHERE (menu_category = 'SEAS_FAVE_1' OR menu_category = 'SEAS_FAVE_2' OR menu_category = 'SEAS_FAVE_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    print("seasonal_special: ", seasonal_special)
                    smoothies = execute(
                        """
                        SELECT
                            meal_id,
                            meal_name,
                            menu_date,
                            menu_category,
                            menu_meal_id,
                            meal_desc,
                            meal_category,
                            meal_photo_url,
                            meal_price,
                            meal_calories,
                            meal_protein,
                            meal_carbs,
                            meal_fiber,
                            meal_sugar,
                            meal_fat,
                            meal_sat
                        FROM menu
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_id
                        WHERE (menu_category = 'SMOOTHIE_1' OR menu_category = 'SMOOTHIE_2' OR menu_category = 'SMOOTHIE_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    print("smothies: ", smoothies)
                    addon = execute(
                        """
                        SELECT
                            meal_id,
                            meal_name,
                            menu_date,
                            menu_category,
                            menu_meal_id,
                            meal_desc,
                            meal_category,
                            meal_photo_url,
                            meal_price,
                            meal_calories,
                            meal_protein,
                            meal_carbs,
                            meal_fiber,
                            meal_sugar,
                            meal_fat,
                            meal_sat
                        FROM menu
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_id
                        WHERE menu_category LIKE 'ADD_ON_%'
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    print("addon: ", addon)
                    if weekly_special['code'] != 280 or seasonal_special['code'] != 280 or smoothies['code'] != 280 or addon['code'] != 280:
                        print("*******************************************")
                        print("* Cannot run the query for Meals endpoint *")
                        print("*******************************************")
                        response['message'] = 'Internal Server Error.'
                        return response, 500
                    thursday = stamp - timedelta(days=2)

                    today = datetime.now()

                    if today < thursday:
                        # stamp = stamp + timedelta(days=7)
                        weekly_special['result'] = [] if not weekly_special['result'] else weekly_special['result']
                        seasonal_special['result'] = [] if not seasonal_special['result'] else seasonal_special['result']

                        week = {
                            'SaturdayDate': str(stamp.date()),
                            'SundayDate': str((stamp + timedelta(days=1)).date()),
                            'Sunday': str((stamp + timedelta(days=1)).date().strftime('%b %-d')),
                            'Monday': str((stamp + timedelta(days=2)).date().strftime('%b %-d')),
                            'Meals': {
                                'Weekly': {
                                    'Category': "WEEKLY SPECIALS",
                                    'Menu': weekly_special['result']
                                },
                                'Seasonal': {
                                    'Category': "SEASONAL FAVORITES",
                                    'Menu': seasonal_special['result']
                                },
                                'Smoothies': {
                                    'Category': "SMOOTHIES",
                                    'Menu': smoothies['result']
                                }
                            },
                            'Addons': {
                                'Addons': {
                                    'Category': "ADD ONS",
                                    'Menu': addon['result']
                                },
                                'Weekly': {
                                    'Category': "ADD MORE MEALS",
                                    'Menu': weekly_special['result'] + seasonal_special['result']
                                },
                                'Smoothies': {
                                    'Category': "ADD MORE SMOOTHIES",
                                    'Menu': smoothies['result']
                                }
                            }
                        }

                        week['MealQuantities'] = self.getMealQuantities(week)

                        week['AddonPrice'] = self.getAddonPrice(week)


                        index = 'MenuForWeek' + str(i)
                        items[index] = week

                        i += 1


            # Finish Line
            response['message'] = 'Request successful.'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Plans(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            business_id = request.args['business_id']
            query = """
                    # ADMIN QUERY 5: PLANS 
                    SELECT * FROM sf.subscription_items si 
                    -- WHERE itm_business_id = "200-000007"; 
                    WHERE itm_business_id = \'""" + business_id + """\';
                    """
            # return simple_get_execute(query, __class__.__name__, conn)
            return simple_get_execute(query, "Plans", conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class AccountPurchases(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            business_id = request.args['business_id']
            query = """
                    # QUERY 4: LATEST PURCHASES WITH SUBSCRIPTION INFO AND LATEST PAYMENTS AND CUSTOMERS
                    # FOR ACCOUNT PURCHASES SECTION
                    SELECT *
                    FROM sf.lpsilp
                    LEFT JOIN sf.customers c
                        ON lpsilp.pur_customer_id = c.customer_uid
                    WHERE pur_business_id = '""" + business_id + """'
                        AND pur_customer_id = '""" + customer_uid + """';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
class Next_Billing_Date(Resource):
    def get(self):
        try:
            conn = connect()
            business_id = request.args['business_id']
            query = """
                    # QUERY 9: NEXT BILLING DATE  NUMBER OF DELIVERIES  NUMBER OF SKIPS
                    SELECT 
                        purchase_id,
                        start_delivery_date,
                        num_issues,
                        payment_day,
                        item_price,
                        shipping,
                    --     menu_date,
                    -- 	combined_selection
                        sum(IF (combined_selection != "" OR combined_selection IS NULL,1,0)) AS weeks,
                        sum(IF (combined_selection != "SKIP" OR combined_selection IS NULL,1,0)) AS delivered,
                        sum(IF (combined_selection = "SKIP",1,0)) AS skip_amount,
                        num_issues - sum(if (combined_selection != "SKIP" OR combined_selection IS NULL,1,0)) AS remaining,
                        ADDDATE(start_delivery_date, payment_day-3) AS BillingDate,
                        ADDDATE(start_delivery_date, payment_day-3+sum(IF (combined_selection = "SKIP",1,0))*payment_day/num_issues) AS NextBillingDate
                    FROM (
                        SELECT *
                        FROM sf.lpsilp, (SELECT DISTINCT menu_date FROM sf.menu) AS md)
                        AS lpsilpmd
                    LEFT JOIN sf.latest_combined_meal lcm
                        ON lpsilpmd.menu_date = lcm.sel_menu_date AND
                            lpsilpmd.purchase_id = lcm.sel_purchase_id
                    WHERE pur_business_id = '""" + business_id + """'
                        AND menu_date >= start_delivery_date
                        AND menu_date <= CURDATE()
                    GROUP BY purchase_id;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Next_Addon_Charge(Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    # STEP 3 COUNT ADDONS AND MULTIPLY BY MENU PRICE TO DETERMINE AMOUNT AND CHARGE DATE
                    # QUERY 10: ADD-ONS AND NEXT ADD-ON CHARGES
                    SELECT *,
                        COUNT(n) as quantity,
                        COUNT(n) * meal_price AS addon_charge,
                        ADDDATE(last_sel_menu_date, -3) as addon_charge_date
                    FROM (
                        SELECT sel_purchase_id,
                            last_sel_menu_date,
                            substring_index(substring_index(addon_selection,';',n),';',-1) AS addon_selected,
                            n
                        FROM (
                            SELECT sel_purchase_id,
                                MIN(last_menu_date) as last_sel_menu_date,
                                addon_selection
                            FROM sf.latest_combined_meal
                            WHERE SEL_MENU_DATE >= ADDDATE(CURDATE(), 0)  -- remove 28 after testing
                                AND addon_selection IS NOT NULL
                                AND addon_selection != ""
                            GROUP BY sel_purchase_id) 
                            AS addon
                    JOIN numbers ON char_length(addon_selection) - char_length(replace(addon_selection, ';', '')) >= n - 1)
                        AS sub
                    LEFT JOIN menu
                        ON addon_selected = menu_meal_id
                        AND last_sel_menu_date = menu_date
                    GROUP BY sel_purchase_id,
                        sub.addon_selected;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class SelectedMeals(Resource):
    def get(self):
        response = {}
        try:
            conn = connect()

            business_id = request.args['business_id']
            customer_uid = request.args['customer_uid']

            query = """
                    # QUERY 5: LATEST PURCHASES WITH SUBSCRIPTION INFO AND LATEST PAYMENTS AND CUSTOMERS AND MEAL SELECTIONS 
                    # FOR MEAL SELECTION PAGE AND BUTTON COLORS 
                    SELECT * FROM sf.lpsilp 
                    LEFT JOIN sf.customers c 	
                        ON lpsilp.pur_customer_id = c.customer_uid 
                    LEFT JOIN sf.latest_combined_meal AS lcm 	
                        ON lpsilp.purchase_id = lcm.sel_purchase_id 
                    WHERE pur_business_id = '""" + business_id + """'
                        AND pur_customer_id = '""" + customer_uid + """';
                    """
            query_res = execute(query, 'get', conn)

            if (query_res['code'] != 280):
                print("*******************************************")
                print("* Cannot run the query for selected Meals *")
                print("*******************************************")
                response['message'] = 'Internal Server Error.'
                return response, 500
            result = {}
            for purchase in query_res['result']:
                if purchase['purchase_id'] not in result:
                    result[purchase['purchase_id']] = {}

                if purchase['sel_menu_date'] not in result[purchase['purchase_id']]:
                    result[purchase['purchase_id']][purchase['sel_menu_date']] = {}

                result[purchase['purchase_id']][purchase['sel_menu_date']] = {
                    'meals_selected' : purchase['meal_selection'],
                    'addons_selected': purchase['addon_selection'],
                    'delivery_day': purchase['delivery_day']
                }
            response['message'] = "Successful."
            response['result'] = result
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selection (Resource):
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            purchase_id = data['purchase_id']
            items_selected = data['items']

            if data['is_addon'] == True:
                # write to addons selected table
                pass
            else:
                # write to meals selected table
                pass
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)
# Bing API - start
class Coordinates:
    # array of addresses such as
    # ['Dunning Ln, Austin, TX 78746', '12916 Cardinal Flower Drive, Austin, TX 78739', '51 Rainey St., austin, TX 78701']
    def __init__(self, locations):
        self.locations = locations

    # returns an address formatted to be used for the Bing API to get locations
    def formatAddress(self, address):
        output = address.replace(" ", "%20")
        if "." in output:
            output = output.replace(".", "")
        return output

    def calculateFromLocations(self):
        global BING_API_KEY

        params = {
            'key': BING_API_KEY
        }
        coordinates = []
        for address in self.locations:
            formattedAddress = self.formatAddress(address)
            print("address: ", address)
            r = requests.get('http://dev.virtualearth.net/REST/v1/Locations/{}'.format(formattedAddress),
                             '&maxResults=1&key={}'.format(params['key']))
            print("result:", r)
            try:
                results = r.json()
                assert (results['resourceSets'][0]['estimatedTotal'])
                point = results['resourceSets'][0]['resources'][0]['geocodePoints'][0]['coordinates']
                lat, lng = point[0], point[1]
            except:
                lat, lng = None, None

            # appends a dictionary of latitude and longitude points for the given address
            coordinates.append({
                "latitude": lat,
                "longitude": lng
            })
        # prints lat, long points for each address
        for i in coordinates:
            print(i, "\n")
            print(type(["latitude"]))

        # return array of dictionaries containing lat, long points
        return coordinates



def get_latest_purchases(bussiness_id, customer_uid):
    response = {}
    try:
        conn = connect()
        query = """SELECT *
                            FROM sf.purchases pur
                            LEFT JOIN sf.customers c
                            ON pur.customer_id = c.customer_uid
                            LEFT JOIN latest_payment
                            AS pay
                            ON pur.purchase_id = pay.purchase_id
                            WHERE business_id = '""" + bussiness_id + """';"""
        res = execute(query, 'get', conn)
        if res['code'] != 280:
            response['message'] = res['message']
            response['result'] = None
            return response
        for r in res['result']:
            if r['customer_uid'] == customer_uid:
                response['message'] = 'Succeeded'
                response['result'] = r
                return response
        response['message'] = 'Not found'
        response['result'] = None
        return response
    except:
        raise BadRequest('Request failed, please try again later.')
    finally:
        disconnect(conn)

class Latest_purchase_info (Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            business_id = request.args.get('business_id')
            customer_uid = request.args.get('customer_uid')
            res = get_latest_purchases(business_id, customer_uid)
            if res['result'] is None:
                response['message'] = res['message']
                return response, 500
            res['result']['cc_num'] = "XXXXXXXXXXXX" + str(res['result']['cc_num'][:-4])
            response['message'] = "Successful."
            response['result'] = res
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Checkout(Resource):
    def post(self):
        response = {}
        reply = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            customer_uid = data['customer_uid']
            business_id = data['business_id']
            delivery_first_name = data['delivery_first_name']
            delivery_last_name = data['delivery_last_name']
            delivery_email = data['delivery_email']
            delivery_phone = data['delivery_phone']
            delivery_address = data['delivery_address']
            delivery_unit = data['delivery_unit']
            delivery_city = data['delivery_city']
            delivery_state = data['delivery_state']
            delivery_zip = data['delivery_zip']
            delivery_instructions = "'" + data['delivery_instructions'] + "'" if data.get('delivery_instructions') is not None else 'NULL'
            delivery_longitude = data['delivery_longitude']
            delivery_latitude = data['delivery_latitude']

            items = "'[" + "".join(['"' + str(item) + '"' for item in data['items']]) + "]'"
            order_instructions = "'" + data['order_instructions'] + "'" if data.get('order_instructions') is not None else 'NULL'
            purchase_notes = "'" + data['purchase_notes'] + "'" if data.get('purchase_notes') is not None else 'NULL'
            amount_due = data['amount_due']
            amount_discount = data['amount_discount']
            amount_paid = data['amount_paid']
            cc_num = data['cc_num']
            cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']
            purchaseId = get_new_purchaseID(conn)
            if purchaseId[1] == 500:
                response['message'] = "Internal Server Error."
                return response, 500
            paymentId = get_new_paymentID(conn)
            if paymentId[1] == 500:
                response['message'] = "Internal Server Error."
                return response, 500
            # User authenticated
            # check the customer_uid and see what kind of registration.
            # if it was registered by email then check the password.
            customer_query = """SELECT * FROM customers WHERE customer_uid = '""" + data['customer_uid'] + """';"""
            customer_res = execute( customer_query, 'get', conn)

            if customer_res['code'] != 280 or not customer_res['result']:
                response['message'] = "Could not authenticate user"
                return response, 401
            if customer_res['result'][0]['password_hashed'] is not None:
                if customer_res['result'][0]['password_hashed'] != data['salt']:
                    response['message'] = "Could not authenticate user. Wrong Password"
                    return response, 401

            # Validate credit card
            if str(data['cc_num'][0:12]) == "XXXXXXXXXXXX":
                latest_purchase = get_latest_purchases(business_id, customer_uid)
                if latest_purchase['result'] is None:
                    response['message'] = "Credit card number is invalid."
                    return response, 400
                if str(latest_purchase['result']['cc_num'][:-4]) != str(data['cc_num'][:-4]):
                    response['message'] = "Credit card number is invalid."
                    return response, 400
                cc_num = latest_purchase['result']['cc_num']

            # create a stripe charge and make sure that charge is successful before writing it into database
            # we should use Idempotent key to prevent sending multiple payment requests due to connection fail.
            # Also, It is not safe for using Strip Charge API. We should use Stripe Payment Intent API and its SDKs instead.
            try:
                # create a token for stripe
                card_dict = {"number": data['cc_num'], "exp_month": int(data['cc_exp_month']), "exp_year": int(data['cc_exp_year']),"cvc": data['cc_cvv']}
                try:
                    card_token = stripe.Token.create(card=card_dict)
                    stripe_charge = stripe.Charge.create(
                        amount=int(round(float(amount_paid)*100, 0)),
                        currency="usd",
                        source=card_token,
                        description="Charge customer %s for %s" %(data['delivery_first_name'] + " " + data['delivery_last_name'], data['items']))
                except stripe.error.CardError as e:
                    # Since it's a decline, stripe.error.CardError will be caught
                    response['message'] = e.error.message
                    return response, 400

                # update coupon table
                coupon_id = data.get('coupon_id')
                if str(coupon_id) != "" and coupon_id is not None:
                    # update coupon table
                    coupon_id = "'" + coupon_id + "'"
                    coupon_query = """UPDATE coupons SET num_used = num_used + 1
                                WHERE coupon_id =  """ + str(coupon_id) + ";"
                    res = execute(coupon_query, 'post', conn)
                else:
                    coupon_id = 'NULL'
                charge_id = 'NULL' if stripe_charge.get('id') is None else "'" + stripe_charge.get('id') + "'"
                # write into Payments table

                payment_query = '''
                                INSERT INTO sf.payments
                                SET payment_uid = \'''' + paymentId + '''\',
                                    payment_time_stamp = \'''' + getNow() + '''\',
                                    payment_id = \'''' + paymentId + '''\',
                                    pay_purchase_id = \'''' + purchaseId + '''\',
                                    amount_due = \'''' + amount_due + '''\',
                                    amount_discount = \'''' + amount_discount + '''\',
                                    amount_paid = \'''' + amount_paid + '''\',
                                    pay_coupon_id = ''' + coupon_id + ''',
                                    charge_id = ''' + charge_id + ''',
                                    payment_type = 'STRIPE',
                                    info_is_Addon = 'FALSE',
                                    cc_num = \'''' + cc_num + '''\', 
                                    cc_exp_date = \'''' + cc_exp_date + '''\', 
                                    cc_cvv = \'''' + cc_cvv + '''\', 
                                    cc_zip = \'''' + cc_zip + '''\';
                                '''
                reply['payment'] = execute(payment_query, 'post', conn)
                if reply['payment']['code'] != 281:
                    print("*************************************")
                    print("* Cannot write into PAYMENTS table *")
                    print("*************************************")
                    response['message'] = "Internal Server Error"
                    return response, 500
                purchase_query = '''INSERT INTO  sf.purchases
                                        SET purchase_uid = \'''' + purchaseId + '''\',
                                            purchase_date = \'''' + getToday() + '''\',
                                            purchase_id = \'''' + purchaseId + '''\',
                                            purchase_status = 'ACTIVE',
                                            pur_customer_id = \'''' + customer_uid + '''\',
                                            pur_business_id = \'''' + business_id + '''\',
                                            delivery_first_name = \'''' + delivery_first_name + '''\',
                                            delivery_last_name = \'''' + delivery_last_name + '''\',
                                            delivery_email = \'''' + delivery_email + '''\',
                                            delivery_phone_num = \'''' + delivery_phone + '''\',
                                            delivery_address = \'''' + delivery_address + '''\',
                                            delivery_unit = \'''' + delivery_unit + '''\',
                                            delivery_city = \'''' + delivery_city + '''\',
                                            delivery_state = \'''' + delivery_state + '''\',
                                            delivery_zip = \'''' + delivery_zip + '''\',
                                            delivery_instructions = ''' + delivery_instructions + ''',
                                            delivery_longitude = \'''' + delivery_longitude + '''\',
                                            delivery_latitude = \'''' + delivery_latitude + '''\',
                                            items = ''' + items + ''',
                                            order_instructions = ''' + order_instructions + ''',
                                            purchase_notes = ''' + purchase_notes + ''';'''
                print(purchase_query)
                reply['purchase'] = execute(purchase_query, 'post', conn)
                if reply['purchase']['code'] != 281:
                    print("*************************************")
                    print("* Cannot write into PURCHASES table *")
                    print("*************************************")
                    execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                    response['message'] = "Internal Server Error"
                    return response, 500
                response['message'] = 'Request successful.'
                response['result'] = reply
                return response, 200
            except:
                if "paymentId" in locals() and "purchaseId" in locals():
                    execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                    execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn)
                response['message'] = "Payment process error."
                return response, 500
        except:
            if "paymentId" in locals() and "purchaseId" in locals():
                execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn)
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# ---------- ADMIN ENDPOINTS ----------------#
# admin endpoints start from here            #
#--------------------------------------------#

# Endpoint for Create/Edit menu
class Get_Menu (Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            date = request.args.get('date')

            queries = ["""
                    SELECT * FROM sf.menu
                    LEFT JOIN sf.meals m
                        ON menu.menu_meal_id = m.meal_id;
                    """
                    ,
                     """
                     SELECT * FROM sf.menu
                     LEFT JOIN sf.meals m
                        ON menu.menu_meal_id = m.meal_id
                     WHERE menu.menu_date = '""" + str(date) + """';
                     """]

            if date is None:
                return simple_get_execute(queries[0], __class__.__name__, conn)
            else:
                return simple_get_execute(queries[1], __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, Please try again later.")
        finally:
            disconnect(conn)

class Get_Meals (Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            query = """
                    SELECT * FROM sf.meals m;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_Coupon(Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            query = """
                    # ADMIN QUERY 6: COUPONS
                    SELECT * FROM sf.coupons cup
                    WHERE cup.cup_business_id IS NULL;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_Orders_By_Purchase_Id(Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            business_id = request.args['business_id']
            query = """
                    # ADMIN QUERY 8: ORDERS BY PURCHASE_ID
                    SELECT *,
                        COUNT(n) as quantity
                    FROM (
                        SELECT purchase_id,
                            menu_date,
                            substring_index(substring_index(final_selection,';',n),';',-1) AS final_meals_selected,
                            n
                        FROM (# QUERY 2: MASTER QUERY:  WHO ORDERED WHAT INCLUDING DEFAULTS AND SELECTIONS
                              # MODIFIED TO SHOW ONLY PURCHASE_ID, MENU_DATE AND FINAL_MEAL_SELECTIONS
                            SELECT 
                                purchase_id,
                                menu_date,
                                CASE
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 5  THEN  def_5_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 10  THEN  def_10_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 15  THEN  def_15_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 20  THEN  def_20_meal
                                    ELSE meal_selection
                                    END 
                                    AS final_selection
                            FROM (
                                SELECT *
                                FROM sf.lpsilp,
                                    sf.default_meal)
                                AS lpsilpdm
                            LEFT JOIN sf.latest_combined_meal AS lcm
                                ON lpsilpdm.purchase_id = lcm.sel_purchase_id AND
                                    lpsilpdm.menu_date = lcm.sel_menu_date
                            WHERE lpsilpdm.pur_business_id = '""" + business_id + """') 
                            AS final_meals
                        JOIN numbers ON char_length(final_selection) - char_length(replace(final_selection, ';', '')) >= n - 1)
                            AS sub
                    GROUP BY purchase_id,
                        menu_date,
                        final_meals_selected;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_Orders_By_Menu_Date (Resource):
    def get(self):
        try:
            conn = connect()
            business_id = request.args['business_id']
            query = """
                    # ADMIN QUERY 9: ORDERS BY MENU_DATE
                    SELECT *,
                        COUNT(n) as quantity
                    FROM (
                        SELECT menu_date,
                            substring_index(substring_index(final_selection,';',n),';',-1) AS final_meals_selected,
                            n
                        FROM (# QUERY 2: MASTER QUERY:  WHO ORDERED WHAT INCLUDING DEFAULTS AND SELECTIONS
                              # MODIFIED TO SHOW ONLY PURCHASE_ID, MENU_DATE AND FINAL_MEAL_SELECTIONS
                            SELECT
                                purchase_id,
                                menu_date,
                                CASE
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 5  THEN  def_5_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 10  THEN  def_10_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 15  THEN  def_15_meal
                                    WHEN (combined_selection IS NULL OR meal_selection = "SURPRISE") AND num_items = 20  THEN  def_20_meal
                                    ELSE meal_selection
                                    END
                                    AS final_selection
                            FROM (
                                SELECT *
                                FROM sf.lpsilp,
                                    sf.default_meal)
                                AS lpsilpdm
                            LEFT JOIN sf.latest_combined_meal AS lcm
                                ON lpsilpdm.purchase_id = lcm.sel_purchase_id AND
                                    lpsilpdm.menu_date = lcm.sel_menu_date
                            WHERE lpsilpdm.pur_business_id = '""" + business_id + """')
                            AS final_meals
                        JOIN numbers ON char_length(final_selection) - char_length(replace(final_selection, ';', '')) >= n - 1)
                            AS sub
                    GROUP BY menu_date,
                        final_meals_selected;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Add_New_Ingredient(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            ingredient_measure_id = data['ingredient_measure_id']
            ingredient_cost = data['ingredient_cost']

            ingredientIdQuery = execute(
                """CALL get_new_ingredient_id();""", 'get', conn)

            ingredientId = ingredientIdQuery['result'][0]['new_id']

            query = """INSERT INTO ingredients (
                                                ingredient_id, ingredient_desc, package_size, ingredient_measure_id,ingredient_cost, ingredient_measure
                                                ) 
                                                SELECT \'""" + str(ingredientId) + """\', \'""" + str(ingredient_desc) + """\',
                                                \'""" + str(package_size) + """\',\'""" + str(ingredient_measure_id) + """\',
                                                \'""" + str(ingredient_cost) + """\', mu.recipe_unit 
                                                FROM conversion_units mu
                                                WHERE measure_unit_id=\'""" + str(ingredient_measure_id) + """\';"""
            print(query)
            items['new_ingredient_insert'] = execute(query, 'post', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" SELECT
                                *
                                FROM
                                ingredients;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class All_Payments(Resource):
    def get(self, user_id):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(
                """ select acc.*,pur.*,mp.meal_plan_desc,
                        pay.*
                        from customers acc
                        left join purchases pur
                        on acc.customer_id = pur.customer_id
                        left join payments pay
                        on pay.purchase_id = pur.purchase_id
                        left join meal_plans mp
                        on pur.meal_plan_id = mp.meal_plan_id
                        where acc.customer_id = '""" + user_id + """'
                        order by pur.purchase_id
                        ;""", 'get', conn)

            response['message'] = 'successful'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class DisplaySaturdays(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()
            items = execute(""" (select * from saturdays where Saturday < CURDATE() order by Saturday desc limit 4)
                                union all
                                (select * from saturdays where Saturday > CURDATE() order by Saturday limit 4);""", 'get', conn)
            response['message'] = 'successful'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def patch(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            Tax_Rate = data['Tax_Rate']
            Saturday = data['Saturday']

            items['update_tax'] = execute("""UPDATE ptyd_saturdays
                                            SET Tax_Rate = \'""" + str(Tax_Rate) + """\'
                                            WHERE Saturday >= \'""" + str(Saturday) + """\';
                                            """, 'post', conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_All_Units(Resource):

    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" SELECT
                               *
                                FROM
                               conversion_units;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Latest_activity(Resource):
    def get(self, user_id):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(
                """ select acc.*,pur.*,mp.meal_plan_desc,
                        pay.*
                        from customers acc
                        left join purchases pur
                        on acc.customer_id = pur.customer_id
                        left join payments pay
                        on pay.purchase_id = pur.purchase_id
                        left join meal_plans mp
                        on pur.meal_plan_id = mp.meal_plan_id
                        where acc.customer_id = '""" + user_id + """'
                        and pay.payment_timestamp in
                        (select latest_time_stamp from
                            (SELECT purchase_id, MAX(payment_timestamp) as "latest_time_stamp" FROM
                                (SELECT * FROM payments where purchase_id = '""" + user_id + """') temp
                                group by purchase_id) temp1
                        )
                        order by pur.purchase_id
                        ;
                        """, 'get', conn)

            response['message'] = 'successful'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class MealCreation(Resource):
    def listIngredients(self, result):
        response = {}
        for meal in result:
            key = meal['meal_id']
            if key not in response:
                response[key] = {}
                response[key]['meal_name'] = meal['meal_name']
                response[key]['ingredients'] = []
            ingredient = {}
            ingredient['name'] = meal['ingredient_desc']
            ingredient['qty'] = meal['recipe_ingredient_qty']
            ingredient['units'] = meal['recipe_unit']
            ingredient['ingredient_id'] = meal['ingredient_id']
            ingredient['measure_id'] = meal['recipe_measure_id']
            response[key]['ingredients'].append(ingredient)

        return response

    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            query = """SELECT
                            m.meal_id,
                            m.meal_name,
                            ingredient_id,
                            ingredient_desc,
                            recipe_ingredient_qty,
                            recipe_unit,
                            recipe_measure_id
                            FROM
                            meals m
                            left JOIN
                            recipes r
                            ON
                            recipe_meal_id = meal_id
                            left JOIN
                            ingredients
                            ON
                            ingredient_id = recipe_ingredient_id
                            left JOIN
                            conversion_units
                            ON                    
                            recipe_measure_id = measure_unit_id
                            order by recipe_meal_id;"""

            sql = execute(query, 'get', conn)

            items = self.listIngredients(sql['result'])

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            # Post JSON needs to be in this format
            #           data = {
            #               'meal_id': '700-000001',
            #               'ingredient_id': '110-000002',
            #               'ingredient_qty': 3,
            #               'measure_id': '130-000004'
            #           }

            query = """
                INSERT INTO ptyd_recipes (
                    recipe_meal_id,
                    recipe_ingredient_id,
                    recipe_ingredient_qty,
                    recipe_measure_id )
                VALUES (
                    \'""" + data['meal_id'] + """\',
                    \'""" + data['ingredient_id'] + """\',
                    \'""" + data['ingredient_qty'] + """\',
                    \'""" + data['measure_id'] + """\')
                ON DUPLICATE KEY UPDATE
                    recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
                    recipe_measure_id = \'""" + data['measure_id'] + "\';"

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class All_Ingredients(Resource):
    global RDS_PW

    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()
            # data = request.get_json(force=True)
            date = request.args.get("date")
            # date_affected = data['date_affected']

            items = execute("""SELECT
                                meals_ordered.week_affected,
                                meals_ordered.total,
                                sum(rec.recipe_ingredient_qty),
                                (meals_ordered.total * sum(rec.recipe_ingredient_qty)) AS total_needed,
                                unit.recipe_unit,
                                ing.ingredient_desc,
                                ing.package_size,
                                ing.package_measure,
                                (select unit.conversion_ratio from conversion_units unit where unit.measure_unit_id = rec.recipe_measure_id) as ratio1,
                                (select unit.type from conversion_units unit where unit.measure_unit_id = rec.recipe_measure_id) as recipe_type,
                                (select unit.conversion_ratio from conversion_units unit where unit.measure_unit_id = ing.package_unit) as measure_type,
                                (select unit.type from conversion_units unit where unit.measure_unit_id = ing.package_unit) as type2,
                                ROUND( (meals_ordered.total * sum(rec.recipe_ingredient_qty)) * unit.conversion_ratio / ing.package_size * (1/(select unit.conversion_ratio from conversion_units unit where unit.measure_unit_id = ing.package_unit)),2) AS need_qty,
								inv.inventory_qty,
								if(ROUND( (meals_ordered.total * sum(rec.recipe_ingredient_qty)) * unit.conversion_ratio / ing.package_size * (1/(select unit.conversion_ratio from conversion_units unit where unit.measure_unit_id = ing.package_unit)),2) - inv.inventory_qty < 0,0,
								abs(inv.inventory_qty - ROUND( (meals_ordered.total * sum(rec.recipe_ingredient_qty)) * unit.conversion_ratio / ing.package_size * (1/(select unit.conversion_ratio from conversion_units unit where unit.measure_unit_id = ing.package_unit)),2))) AS buy_qty       
                            FROM (# QUERY 11
                                SELECT 
                                    week_affected,
                                    meal_selected,
                                    meal_name,
                                    COUNT(num) AS total
                                FROM (
                                    SELECT *
                                        , substring_index(substring_index(combined_selection,';',n),';',-1) AS meal_selected
                                        , n AS num
                                    FROM (# QUERY 8
                                        SELECT meals.*,
                                            addons.meal_selection AS addon_selection,
                                            if(addons.meal_selection IS NOT NULL,CONCAT(meals.meal_selection,';',addons.addons.meal_selection),meals.meal_selection) AS combined_selection
                                        FROM (# QUERY 7
                                            SELECT
                                                act_meal.purchase_id,
                                                act_meal.Saturday AS week_affected,
                                                act_meal.delivery_first_name,
                                                act_meal.delivery_last_name,
                                                act_meal.num_meals,
                                                act_meal.deliver AS delivery_day,
                                                -- act_meal.meal_selection AS org_meal_selection,
                                                CASE
                                                    WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 5  THEN  act_meal.def_5_meal
                                                    WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 10 THEN act_meal.def_10_meal
                                                    WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 15 THEN act_meal.def_15_meal
                                                    WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 20 THEN act_meal.def_20_meal
                                                    ELSE act_meal.meal_selection
                                                END AS meal_selection
                                            FROM (# QUERY 6
                                                SELECT 
                                                    sel_meals.*,
                                                    CASE
                                                        WHEN (sel_meals.delivery_day IS NULL) THEN  "Sunday"
                                                        #WHEN (sel_meals.delivery_day IS NULL AND sel_meals.delivery_default_day IS NOT NULL ) THEN sel_meals.delivery_default_day
                                                        ELSE sel_meals.delivery_day
                                                    END AS deliver,
                                                    plans.num_meals,
                                                    plans.meal_weekly_price,
                                                    plans.meal_plan_price,
                                                    def_meals.*
                                                FROM (# QUERY 4
                                                    SELECT 
                                                        act_pur.*,
                                                        act_meal.selection_time,
                                                        act_meal.meal_selection,
                                                        act_meal.delivery_day
                                                    FROM (
                                                        SELECT * 
                                                        FROM purchases pur
                                                        JOIN saturdays sat
                                                        WHERE pur.purchase_status = "ACTIVE"
                                                            -- AND sat.Saturday < "2020-09-01"
                                                            AND sat.Saturday > DATE_ADD(CURDATE(), INTERVAL -16 DAY)
                                                            AND sat.Saturday < DATE_ADD(CURDATE(), INTERVAL 40 DAY)
                                                           -- AND sat.Saturday > pur.start_date)
                                                            AND DATE_ADD(sat.Saturday, INTERVAL 0 DAY) > DATE_ADD(pur.start_date, INTERVAL 2 DAY))
                                                        AS act_pur
                                                    LEFT JOIN (# QUERY 1 
                                                        SELECT
                                                            ms1.purchase_id
                                                            , ms1.selection_time
                                                            , ms1.week_affected
                                                            , ms1.meal_selection
                                                            , ms1.delivery_day
                                                        FROM meals_selected AS ms1
                                                        INNER JOIN (
                                                            SELECT
                                                                purchase_id
                                                                , week_affected
                                                                , meal_selection
                                                                , MAX(selection_time) AS latest_selection
                                                                , delivery_day
                                                            FROM meals_selected
                                                            GROUP BY purchase_id
                                                                , week_affected)
                                                            AS ms2 
                                                        ON ms1.purchase_id = ms2.purchase_id 
                                                            AND ms1.week_affected = ms2.week_affected 
                                                            AND ms1.selection_time = ms2.latest_selection
                                                        ORDER BY purchase_id
                                                            , week_affected)
                                                        AS act_meal
                                                    ON act_pur.Saturday = act_meal.week_affected
                                                        AND act_pur.purchase_id = act_meal.purchase_id
                                                    ORDER BY act_pur.purchase_id
                                                        , act_pur.Saturday
                                                        , act_meal.selection_time)
                                                    AS sel_meals
                                                LEFT JOIN meal_plans AS plans ON sel_meals.meal_plan_id = plans.meal_plan_id    
                                                LEFT JOIN (# QUERY 5
                                                    SELECT dm.*
                                                        , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 59,10)) 
                                                                as def_5_meal
                                                        , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10)) 
                                                                as def_10_meal
                                                        , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10)) 
                                                                as def_15_meal
                                                        , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals,  3,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 17,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 31,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 45,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10),";"
                                                                ,MID(dm.default_meals, 59,10)) 
                                                                as def_20_meal
                                                    FROM (
                                                        SELECT defaultmeal.menu_date
                                                            , defaultmeal.menu_category
                                                            , defaultmeal.menu_type
                                                            , defaultmeal.meal_cat
                                                            , JSON_ARRAYAGG(menu_meal_id) as "default_meals" 
                                                            
                                                        FROM (
                                                            SELECT * FROM menu menu
                                                            WHERE default_meal = "TRUE")
                                                            AS defaultmeal
                                                        GROUP BY defaultmeal.menu_date)
                                                        AS dm)
                                                    AS def_meals
                                                ON sel_meals.Saturday = def_meals.menu_date)
                                                AS act_meal)
                                            AS meals
                                        LEFT JOIN (# QUERY 2
                                            SELECT
                                                ms1.purchase_id,
                                                -- , ms1.selection_time
                                                ms1.week_affected,
                                                "Add-on" AS delivery_first_name,
                                                "Add-on" AS delivery_last_name,
                                                "0" AS num_meals,
                                                "Add-on" AS delivery_day,
                                                ms1.meal_selection
                                            FROM addons_selected AS ms1
                                            INNER JOIN (
                                                SELECT
                                                    purchase_id
                                                    , week_affected
                                                    , meal_selection
                                                    , MAX(selection_time) AS latest_selection
                                                FROM addons_selected
                                                GROUP BY purchase_id
                                                    , week_affected
                                            ) as ms2 
                                            ON ms1.purchase_id = ms2.purchase_id 
                                                AND ms1.week_affected = ms2.week_affected 
                                                AND ms1.selection_time = ms2.latest_selection
                                            ORDER BY purchase_id
                                                , week_affected)
                                            AS addons
                                            ON meals.purchase_id = addons.purchase_id
                                            AND meals.week_affected = addons.week_affected
                                        GROUP BY meals.purchase_id,
                                            meals.week_affected)
                                        AS combined
                                JOIN numbers ON char_length(combined_selection) - char_length(replace(combined_selection, ';', '')) >= n - 1)
                                    AS sub
                                LEFT JOIN meals meals ON sub.meal_selected = meals.meal_id
                                GROUP BY week_affected
                                    , meal_selected
                                ORDER BY week_affected
                                    , meal_selected)
                                AS meals_ordered
                            LEFT JOIN recipes rec ON meals_ordered.meal_selected = rec.recipe_meal_id
                            JOIN conversion_units unit ON rec.recipe_measure_id = unit.measure_unit_id
                            LEFT JOIN ingredients ing ON rec.recipe_ingredient_id = ing.ingredient_id
                            #LEFT JOIN measure_conversion mc ON rec.recipe_measure_id = mc.from_measure_unit_id AND ing.ingredient_measure_id = mc.to_measure_unit_id
                            LEFT JOIN inventory inv ON rec.recipe_ingredient_id = inv.inventory_ingredient_id
                            #and inv.inventory_measure_id = unit.measure_unit_id
                            GROUP BY rec.recipe_ingredient_id,
                                meals_ordered.week_affected
                            ORDER BY meals_ordered.week_affected,
                                ingredient_desc;""", 'get', conn)

            response['message'] = 'successful'
            response['result'] = items
            print("Ingredients:")
            print(items)

            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class All_Meals(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()
            # data = request.get_json(force=True)
            date = request.args.get("date")
            # date_affected = data['date_affected']

            items = execute("""
                            # QUERY 12 ADMIN PAGE QUERY SHOWING ALL MENUS, MEALS AND QUANTITIES ORDERED (SELECTED, ADDONS AND SURPRISE)
                                SELECT 
                                    allmeals.*,
                                    meals_ordered.total
                                    FROM (# QUERY 8
                                    SELECT 
                                        menu_date,
                                        menu_category,
                                        meal_category,
                                        menu_type,
                                        meal_cat,
                                        meal_id,
                                        meals.meal_name,
                                        default_meal,
                                        extra_meal_price
                                    FROM menu menu
                                    JOIN meals meals
                                        ON menu.menu_meal_id = meals.meal_id )
                                        AS allmeals
                                LEFT JOIN   (# QUERY 9
                                    SELECT 
                                        week_affected,
                                        meal_selected,
                                        meal_name,
                                        COUNT(num) AS total
                                    FROM (
                                        SELECT *
                                            , substring_index(substring_index(combined_selection,';',n),';',-1) AS meal_selected
                                            , n AS num
                                        FROM (# QUERY 8
                                            SELECT meals.*,
                                                addons.meal_selection AS addon_selection,
                                                if(addons.meal_selection IS NOT NULL,CONCAT(meals.meal_selection,';',addons.addons.meal_selection),meals.meal_selection) AS combined_selection
                                            FROM (# QUERY 7
                                                SELECT
                                                    act_meal.purchase_id,
                                                    act_meal.Saturday AS week_affected,
                                                    act_meal.delivery_first_name,
                                                    act_meal.delivery_last_name,
                                                    act_meal.num_meals,
                                                    act_meal.deliver AS delivery_day,
                                                    -- act_meal.meal_selection AS org_meal_selection,
                                                    CASE
                                                        WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 5  THEN  act_meal.def_5_meal
                                                        WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 10 THEN act_meal.def_10_meal
                                                        WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 15 THEN act_meal.def_15_meal
                                                        WHEN (act_meal.meal_selection IS NULL OR act_meal.meal_selection = "SURPRISE") AND act_meal.num_meals = 20 THEN act_meal.def_20_meal
                                                        ELSE act_meal.meal_selection
                                                    END AS meal_selection
                                                FROM (# QUERY 6
                                                    SELECT 
                                                        sel_meals.*,
                                                        CASE
                                                            WHEN (sel_meals.delivery_day IS NULL) THEN  "Sunday"
                                                            #WHEN (sel_meals.delivery_day IS NULL AND sel_meals.delivery_default_day IS NOT NULL ) THEN sel_meals.delivery_default_day
                                                            ELSE sel_meals.delivery_day
                                                        END AS deliver,
                                                        plans.num_meals,
                                                        plans.meal_weekly_price,
                                                        plans.meal_plan_price,
                                                        def_meals.*
                                                    FROM (# QUERY 4
                                                        SELECT 
                                                            act_pur.*,
                                                            act_meal.selection_time,
                                                            act_meal.meal_selection,
                                                            act_meal.delivery_day
                                                        FROM (
                                                            SELECT * 
                                                            FROM purchases pur
                                                            JOIN saturdays sat
                                                            WHERE pur.purchase_status = "ACTIVE"
                                                                -- AND sat.Saturday < "2020-09-01"
                                                                AND sat.Saturday > DATE_ADD(CURDATE(), INTERVAL -16 DAY)
                                                                AND sat.Saturday < DATE_ADD(CURDATE(), INTERVAL 40 DAY)
                                                               -- AND sat.Saturday > pur.start_date)
                                                                AND DATE_ADD(sat.Saturday, INTERVAL 0 DAY) > DATE_ADD(pur.start_date, INTERVAL 2 DAY))
                                                            AS act_pur
                                                        LEFT JOIN (# QUERY 1 
                                                            SELECT
                                                                ms1.purchase_id
                                                                , ms1.selection_time
                                                                , ms1.week_affected
                                                                , ms1.meal_selection
                                                                , ms1.delivery_day
                                                            FROM meals_selected AS ms1
                                                            INNER JOIN (
                                                                SELECT
                                                                    purchase_id
                                                                    , week_affected
                                                                    , meal_selection
                                                                    , MAX(selection_time) AS latest_selection
                                                                    , delivery_day
                                                                FROM meals_selected
                                                                GROUP BY purchase_id
                                                                    , week_affected)
                                                                AS ms2 
                                                            ON ms1.purchase_id = ms2.purchase_id 
                                                                AND ms1.week_affected = ms2.week_affected 
                                                                AND ms1.selection_time = ms2.latest_selection
                                                            ORDER BY purchase_id
                                                                , week_affected)
                                                            AS act_meal
                                                        ON act_pur.Saturday = act_meal.week_affected
                                                            AND act_pur.purchase_id = act_meal.purchase_id
                                                        ORDER BY act_pur.purchase_id
                                                            , act_pur.Saturday
                                                            , act_meal.selection_time)
                                                        AS sel_meals
                                                    LEFT JOIN meal_plans AS plans ON sel_meals.meal_plan_id = plans.meal_plan_id    
                                                    LEFT JOIN (# QUERY 5
                                                        SELECT dm.*
                                                            , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 59,10)) 
                                                                    as def_5_meal
                                                            , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10)) 
                                                                    as def_10_meal
                                                            , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10)) 
                                                                    as def_15_meal
                                                            , CONCAT(MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals,  3,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 17,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 31,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 45,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10),";"
                                                                    ,MID(dm.default_meals, 59,10)) 
                                                                    as def_20_meal
                                                        FROM (
                                                            SELECT defaultmeal.menu_date
                                                                , defaultmeal.menu_category
                                                                , defaultmeal.menu_type
                                                                , defaultmeal.meal_cat
                                                                , JSON_ARRAYAGG(menu_meal_id) as "default_meals" 
                                                                
                                                            FROM (
                                                                SELECT * FROM menu menu
                                                                WHERE default_meal = "TRUE")
                                                                AS defaultmeal
                                                            GROUP BY defaultmeal.menu_date)
                                                            AS dm)
                                                        AS def_meals
                                                    ON sel_meals.Saturday = def_meals.menu_date)
                                                    AS act_meal)
                                                AS meals
                                            LEFT JOIN (# QUERY 2
                                                SELECT
                                                    ms1.purchase_id,
                                                    -- , ms1.selection_time
                                                    ms1.week_affected,
                                                    "Add-on" AS delivery_first_name,
                                                    "Add-on" AS delivery_last_name,
                                                    "0" AS num_meals,
                                                    "Add-on" AS delivery_day,
                                                    ms1.meal_selection
                                                FROM addons_selected AS ms1
                                                INNER JOIN (
                                                    SELECT
                                                        purchase_id
                                                        , week_affected
                                                        , meal_selection
                                                        , MAX(selection_time) AS latest_selection
                                                    FROM addons_selected
                                                    GROUP BY purchase_id
                                                        , week_affected
                                                ) as ms2 
                                                ON ms1.purchase_id = ms2.purchase_id 
                                                    AND ms1.week_affected = ms2.week_affected 
                                                    AND ms1.selection_time = ms2.latest_selection
                                                ORDER BY purchase_id
                                                    , week_affected)
                                                AS addons
                                                ON meals.purchase_id = addons.purchase_id
                                                AND meals.week_affected = addons.week_affected
                                            GROUP BY meals.purchase_id,
                                                meals.week_affected)
                                            AS combined
                                    JOIN numbers ON char_length(combined_selection) - char_length(replace(combined_selection, ';', '')) >= n - 1)
                                        AS sub
                                    LEFT JOIN meals meals ON sub.meal_selected = meals.meal_id
                                    GROUP BY week_affected
                                        , meal_selected
                                    ORDER BY week_affected
                                        , meal_selected)
                                                                        AS meals_ordered
                                        ON allmeals.menu_date = meals_ordered.week_affected
                                                                            AND allmeals.meal_id = meals_ordered.meal_selected
                                                                    where menu_date = \'""" + date + """\'
                                                                    ORDER BY 
                                                                        menu_date,
                                                                        menu_category
                                    ;""", 'get', conn)

            response['message'] = 'successful'
            response['result'] = items
            # print(items)

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class SavePurchaseNote(Resource):
    def post(self, purchase_id):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            updatedNote = data['note']
            items = execute(
                '''
                    UPDATE purchases
                    SET admin_notes = \'''' + str(updatedNote) + '''\'
                    WHERE purchase_id = \'''' + str(purchase_id) + '''\';
                '''
            ,'post',conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# Define API routes
# Customer APIs

#---------------------------- Select Meal plan pages ----------------------------#
#  * The "plans" endpoint accepts only get request without any parameter. It will#
# return all the meal plans in the SUBSCRIPTION_ITEM table. The returned info    #
# contains all meal plans (which is grouped by item's name) and its associated   #
# details.                                                                       #
api.add_resource(Plans, '/api/v2/plans')
#--------------------------------------------------------------------------------#

#---------------------------- Signup/ Login page --------------------------------#
#  * The "signup" endpoint accepts only POST request with appropriate named      #
#  parameters. Please check the documentation for the right format of those named#
#  parameters.                                                                   #
api.add_resource(SignUp, '/api/v2/signup')

api.add_resource(Login, '/api/v2/login')
#--------------------------------------------------------------------------------#

#------------- Checkout, Meal Selection and Meals Schedule pages ----------------#
#  * The "Meals" endpoint only accepts GET request with an optional parameter. It#
# will return the whole available menu info. If the "startDate" param is given.  #
# The returning menu info only contain the menu which starts from that date.     #
# Notice that the optional parameter must go after the slash.
api.add_resource(Meals, '/api/v2/meals', '/api/v2/meals/<string:startDate>')
#  * The "accountsalt" endpoint accepts only GET request with a required param.  #
#  It will return the information of password hased and password salt for an     #
# associated email account.
api.add_resource(AccountSalt, '/api/v2/accountsalt')
#  * The "accountpurchases" only accepts GET request with 2 required parameters. #
#  It will return the information of all current purchases of a specific customer#
#  of a specific business. Accepting arguments for this endpoints are:           #
#  "customer_id", "business_id".                                                 #
api.add_resource(AccountPurchases, '/api/v2/accountpurchases')
#  * The "next_billing_date" only accepts GET request with 1 required parameter. #
#  It will return the information of the next billing date of a specific business#
# The required parameter is: "business_id
api.add_resource(Next_Billing_Date, '/api/v2/next_billing_date')
#  * The "next_addon_charge" only accepts GET request without any parameter. It  #
# will return the next addon charge information.
api.add_resource(Next_Addon_Charge, '/api/v2/next_addon_charge')
#  * The "selectedmeals" only accepts GET request with two required arguments:   #
# "customer_id" and "business_id".It will return the information of all selected #
# meals and addons which are associated with the specific purchase.              #
api.add_resource(SelectedMeals, '/api/v2/selectedmeals')
#  * The "checkout" accepts POST request with appropriate arguments. Please read #
# the documentation for these arguments and its formats.                         #
api.add_resource(Meals_Selection, '/api/v2/meals_selection')
api.add_resource(Checkout, '/api/v2/checkout')
#--------------------------------------------------------------------------------#



# Admin APIs
#---------------------------- Create / Edit Menu pages ---------------------------#
#  * The get_menu endpoint accepts only get request and returns the menu's        #
#  information. If there is a given param (named "date") in the get request.      #
#  The returned info will associate with that "date" otherwise all information in #
#  the menu table will be returned.                                               #
api.add_resource(Get_Menu, '/api/v2/get_menu')
#  * The get_meals endpoint accepts only get request and return all associate     #
#   info. This endpoint does not accept any argument.                             #
# Notice: these two endpoint will replace the old three ones that were using in   #
# PTYD website. from these two endpoint, the front end can extract whatever info  #
# it needs.                                                                       #
api.add_resource(Get_Meals, '/api/v2/get_meals')
#---------------------------------------------------------------------------------#

#-------------------------------- Plan / Coupon pages ----------------------------#
#  * The user can access /api/v2/plans endpoint to get all Plans.                 #
#  * The Get_coupon endpoint accepts only GET request with a required argument    #
#  ("business_id"). This endpoint will returns all active coupons in the COUPON   #
#  table.                                                                         #
api.add_resource(Get_Coupon, '/api/v2/get_coupons')

#  * The Get_Orders_By_Purchase_id endpoint accepts only GET request without any  #
#  parameters. It will return meal orders based on the purchase_id.               #
api.add_resource(Get_Orders_By_Purchase_Id, '/api/v2/get_orders_by_purchases_id')
#  * The Get_Orders_By_Menu_Date endpoint accepts only GET request without any    #
#  parameters. It will return meal orders based on the menu date.                 #
api.add_resource(Get_Orders_By_Menu_Date, '/api/v2/get_orders_by_menu_date')


#***********************************************************************************
# The endpoints below have not been tested. Just moved from old PTYD               *
#***********************************************************************************
api.add_resource(Add_New_Ingredient, '/api/v2/Add_New_Ingredient')
api.add_resource(All_Payments, '/api/v2/All_Payments/<string:user_id>')
api.add_resource(DisplaySaturdays, '/api/v2/saturdays')
api.add_resource(Get_All_Units, '/api/v2/GetUnits')
api.add_resource(Latest_activity, '/api/v2/Latest_activity/<string:user_id>')
api.add_resource(MealCreation, '/api/v2/mealcreation')
api.add_resource(All_Ingredients, '/api/v2/All_Ingredients')
api.add_resource(All_Meals, '/api/v2/All_Meals')
api.add_resource(SavePurchaseNote,'/api/v2/SavePurchaseNote/<string:purchase_id>')
#***********************************************************************************

# Run on below IP address and port
# Make sure port number is unused (i.e. don't use numbers 0-1023)
# lambda function at: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=2000)

