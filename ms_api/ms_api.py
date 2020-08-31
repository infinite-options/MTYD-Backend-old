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
#regex
import re
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
        query_number = "    " + re.search(r'#(.*?):', query).group(1) + "     "
        string = " Cannot run the query for " + name_to_show + "."
        print("\n")
        print("*" * (len(string) + 10))
        print(string.center(len(string) + 10, "*"))
        print(query_number.center(len(string) + 10, "*"))
        print("*" * (len(string) + 10), "\n")
        response['message'] = 'Internal Server Error.'
        return response, 500
    elif not res['result']:
        response['message'] = 'Not Found'
        return response, 404
    else:
        response['message'] = "Get " + name_to_show + " successful."
        response['result'] = res['result']

        return response, 200

def simple_post_execute(queries, names, conn):
    response = {}
    if len(queries) != len(names):
        return "Error. Queries and Names should have the same length."
    for i in range(len(queries)):
        res = execute(queries[i], 'post', conn)
        if res['code'] != 281:
            string = " Cannot Insert into the " + names[i] + " table. "
            print("*" * (len(string) + 10))
            print(string.center(len(string) + 10, "*"))
            print("*" * (len(string) + 10))
            response['message'] = "Internal Server Error."
            return response, 500
    response['message'] = "Post successful."
    return response, 201

class SignUp(Resource):
    def post(self):
        try:
            conn = connect()
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

            response = simple_get_execute(query, "Sigup - Check for Existing Customer", conn)
            if response[1] == 500:
                return response
            elif response[1] == 200:
                response = {
                    'message': "Email address has already taken."
                }
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
                access_token = "'" + data['access_token'] + "'"
                refresh_token = "'" + data['refresh_token'] + "'"
                salt = 'NULL'
                password = 'NULL'
                algorithm = 'NULL'
                user_social_signup = "'" + data['social'] + "'"
            # write everything to database
            customer_insert_query = ["""
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
                                    """]
            response = simple_post_execute(customer_insert_query, ['SIGN_UP'], conn)
            if response[1] != 201:
                return response
            response[0]['result'] = {
                'first_name': firstName,
                'last_name': lastName,
                'customer_uid': NewUserID,
                'access_token': access_token,
                'refresh_token': refresh_token
            }
            # Sending verification email
            if social_signup == False:
                token = s.dumps(email)
                msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[email])
                link = url_for('confirm', token=token, hashed=password, _external=True)
                msg.body = "Click on the link {} to verify your email address.".format(link)
                mail.send(msg)
            return response
        except:
            print("Error happened while Sign Up")
            if "NewUserID" in locals():
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

class Login (Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            email = data['email']
            password = data.get('password')
            refresh_token = data.get('token')
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
            res = simple_get_execute(query, __class__.__name__, conn)
            if res[1] == 500:
                response['message'] = "Internal Server Error."
                return response, 500
            elif res[1] == 404:
                response['message'] = 'Not Found'
                return response, 404
            else:
                if password is not None and res[0]['result'][0]['user_social_media'] == 'TRUE':
                    response['message'] = "Need to login by Social Media"
                    return response, 401
                elif (password is None and refresh_token is None) or (password is None and res[0]['result'][0]['user_social_media'] == 'FALSE'):
                    return BadRequest("Bad request.")
                # compare passwords if user_social_media is false
                elif (res[0]['result'][0]['user_social_media'] == 'FALSE' or res[0]['result'][0]['user_social_media']=="") and password is not None:
                    salt = res[0]['result'][0]['password_salt']
                    hashed = sha512((password + salt).encode()).hexdigest()
                    if res[0]['result'][0]['password_hashed'] != hashed:
                        response['message'] = "Wrong password."
                        return response, 401
                    if (int(res[0]['result'][0]['email_verified']) == 0) or (res[0]['result'][0]['email_verified'] == "FALSE"):
                        response['message'] = "Account need to be verified by email."
                        return response, 401
                # compare the refresh token because it never expire.
                elif (res[0]['result'][0]['user_social_media']) == 'TRUE':
                    if (res[0]['result'][0]['user_refresh_token'] != refresh_token):
                        response['message'] = "Cannot Authenticated. Token is invalid."
                        return response, 401
                else:
                    string = " Cannot compare the password or refresh token while log in. "
                    print("*" * (len(string) + 10))
                    print(string.center(len(string) + 10, "*"))
                    print("*" * (len(string) + 10))
                    response['message'] = 'Internal Server Error.'
                    return response, 500

                del res[0]['result'][0]['password_hashed']
                del res[0]['result'][0]['password_salt']

                response['message'] = "Authenticated success."
                response['result'] = res[0]['result'][0]
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
                    meal_id = eachMeal['meal_uid']
                    mealQuantities[meal_id] = 0
        return mealQuantities
    def getAddonPrice(self, menu):
        savedAddonPrice = {}
        for key in ['Meals', 'Addons']:
            for subMenu in menu[key]:
                for eachMeal in menu[key][subMenu]['Menu']:
                    related_price = eachMeal['meal_price']
                    meal_id = eachMeal['meal_uid']
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
                            meal_uid,
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
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_uid
                        WHERE (menu_category = 'WKLY_SPCL_1' OR menu_category = 'WKLY_SPCL_2' OR menu_category = 'WKLY_SPCL_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    seasonal_special = execute(
                        """
                        SELECT
                            meal_uid,
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
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_uid
                        WHERE (menu_category = 'SEAS_FAVE_1' OR menu_category = 'SEAS_FAVE_2' OR menu_category = 'SEAS_FAVE_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    smoothies = execute(
                        """
                        SELECT
                            meal_uid,
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
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_uid
                        WHERE (menu_category = 'SMOOTHIE_1' OR menu_category = 'SMOOTHIE_2' OR menu_category = 'SMOOTHIE_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    addon = execute(
                        """
                        SELECT
                            meal_uid,
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
                        LEFT JOIN meals ON menu.menu_meal_id = meals.meal_uid
                        WHERE menu_category LIKE 'ADD_ON_%'
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)
                    for res in ["weekly_special", "seasonal_special", "smoothies", "addon"]:
                        if locals()[res]['code'] != 280:
                            string = " Cannot run the query for \"" + res + "\" in Meals endpoint. "
                            print("*" * (len(string) + 10))
                            print(string.center(len(string) + 10, "*"))
                            print("*" * (len(string) + 10))
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
            business_uid = request.args['business_uid']
            query = """
                    # ADMIN QUERY 5: PLANS 
                    SELECT * FROM sf.subscription_items si 
                    -- WHERE itm_business_uid = "200-000007"; 
                    WHERE itm_business_uid = \'""" + business_uid + """\';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
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
            business_uid = request.args['business_uid']
            query = """
                    # QUERY 4: LATEST PURCHASES WITH SUBSCRIPTION INFO AND LATEST PAYMENTS AND CUSTOMERS
                    # FOR ACCOUNT PURCHASES SECTION
                    SELECT *
                    FROM sf.lpsilp
                    LEFT JOIN sf.customers c
                        ON lpsilp.pur_customer_uid = c.customer_uid
                    WHERE pur_business_uid = '""" + business_uid + """'
                        AND pur_customer_uid = '""" + customer_uid + """';
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
            business_uid = request.args['business_uid']
            query = """
                    # QUERY 9: NEXT BILLING DATE  NUMBER OF DELIVERIES  NUMBER OF SKIPS
                    SELECT 
                        purchase_id,
                        start_delivery_date,
                        num_issues,
                        payment_day,
                        item_price,
                        shipping,
                    --  menu_date,
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
                    WHERE pur_business_uid = '""" + business_uid + """'
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
                        SELECT sel_purchase_id,
                            SUM(addon_charge) as total_addon_charge,
                            addon_charge_date
                        FROM (
                        SELECT aos.*, jt.*,
                            jt_qty * jt_price AS addon_charge,
                            ADDDATE(last_sel_menu_date, -3) as addon_charge_date
                        -- FROM sf.purchases AS pur,
                        FROM (# STEP 2
                            SELECT sel_purchase_id,
                                MIN(last_menu_date) as last_sel_menu_date,
                                addon_selection
                            FROM sf.latest_combined_meal
                            WHERE SEL_MENU_DATE >= ADDDATE(CURDATE(), -28)  -- replace 0 with -28 to enable testing
                                AND json_length(addon_selection) != 0
                            GROUP BY sel_purchase_id) 
                            AS aos,
                        JSON_TABLE (aos.addon_selection, '$[*]' 
                            COLUMNS (
                                    jt_id FOR ORDINALITY,
                                    jt_item_uid VARCHAR(255) PATH '$.item_uid',
                                    jt_name VARCHAR(255) PATH '$.name',
                                    jt_qty INT PATH '$.qty',
                                    jt_price DOUBLE PATH '$.price')
                                ) AS jt)
                            AS aosjt
                        GROUP BY sel_purchase_id;
                        """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)


class Meals_Selected(Resource):
    def get(self):
        response = {}
        try:
            conn = connect()
            business_uid = request.args['business_uid']
            customer_uid = request.args['customer_uid']
            query = """
                    # QUERY 5: LATEST PURCHASES WITH SUBSCRIPTION INFO AND LATEST PAYMENTS AND CUSTOMERS AND MEAL SELECTIONS
                    # FOR MEAL SELECTION PAGE AND BUTTON COLORS
                    SELECT *
                    FROM sf.lpsilp
                    LEFT JOIN sf.customers c
                        ON lpsilp.pur_customer_uid = c.customer_uid
                    LEFT JOIN sf.latest_combined_meal AS lcm
                        ON lpsilp.purchase_id = lcm.sel_purchase_id
                    WHERE pur_business_uid = '""" + business_uid + """'
                        AND pur_customer_uid = '""" + customer_uid + """';
                    """
            query_res = simple_get_execute(query, __class__.__name__, conn)
            if query_res[1] == 500:
                response['message'] = "Internal Server Error"
                return response, 500
            elif query_res[1] == 404:
                response['message'] = "Not Found."
                return response, 404
            result = {}
            query_res = query_res[0]
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
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            purchase_id = data['purchase_id']
            items_selected = "'[" + ", ".join([str(item).replace("'", "\"") for item in data['items']]) + "]'"
            delivery_day = data['delivery_day']
            sel_menu_date = data['menu_date']

            if data['is_addon']:
                res = execute("CALL new_addons_selected_uid();", 'get', conn)
            else:
                res = execute("CALL new_meals_selected_uid();", 'get', conn)
            if res['code'] != 280:
                print("*******************************************")
                print("* Cannot run the query to get a new \"selection_uid\" *")
                print("*******************************************")
                response['message'] = 'Internal Server Error.'
                return response, 500
            selection_uid = res['result'][0]['new_id']
            queries = [[
                        """
                        INSERT INTO addons_selected
                        SET selection_uid = '""" + selection_uid + """',
                            sel_purchase_id = '""" + purchase_id + """',
                            selection_time = '""" + getNow() + """',
                            sel_menu_date = '""" + sel_menu_date + """',
                            meal_selection = """ + items_selected + """,
                            delivery_day = '""" + delivery_day + """';
                        """
                        ],
                       [
                       """
                       INSERT INTO meals_selected
                       SET selection_uid = '""" + selection_uid + """',
                        sel_purchase_id = '""" + purchase_id + """',
                        selection_time = '""" + getNow() + """',
                        sel_menu_date = '""" + sel_menu_date + """',
                        meal_selection = """ + items_selected + """,
                        delivery_day = '""" + delivery_day + """';
                        """
                       ]]

            if data['is_addon'] == True:
                # write to addons selected table
                # need a stored function to get the new selection
                response = simple_post_execute(queries[0], ["ADDONS_SELECTED"], conn)
            else:
                response = simple_post_execute(queries[1], ["MEALS_SELECTED"], conn)
            if response[1] == 201:
                response[0]['selection_uid']= selection_uid
            return response
        except:
            if "selection_uid" in locals():
                execute("DELETE FROM addons_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
                execute("DELETE FROM meals_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
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
            items = "'[" + ", ".join([str(item).replace("'", "\"") for item in data['items']]) + "]'"
            order_instructions = "'" + data['order_instructions'] + "'" if data.get('order_instructions') is not None else 'NULL'
            purchase_notes = "'" + data['purchase_notes'] + "'" if data.get('purchase_notes') is not None else 'NULL'
            amount_due = data['amount_due']
            amount_discount = data['amount_discount']
            amount_paid = data['amount_paid']
            cc_num = data['cc_num']
            cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']

            # We should sanitize the variable before writting into database.
            # must pass these check first
            if items == "'[]'":
                raise BadRequest()

            purchaseId = get_new_purchaseID(conn)
            if purchaseId[1] == 500:
                print(purchaseId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            paymentId = get_new_paymentID(conn)
            if paymentId[1] == 500:
                print(paymentId[0])
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

                queries = [
                            '''
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
                                cc_num = \'''' + cc_num  + '''\', 
                                cc_exp_date = \'''' + cc_exp_date + '''\', 
                                cc_cvv = \'''' + cc_cvv + '''\', 
                                cc_zip = \'''' + cc_zip + '''\';
                            ''',
                            '''
                            INSERT INTO  sf.purchases
                            SET purchase_uid = \'''' + purchaseId + '''\',
                                purchase_date = \'''' + getToday() + '''\',
                                purchase_id = \'''' + purchaseId + '''\',
                                purchase_status = 'ACTIVE',
                                pur_customer_uid = \'''' + customer_uid + '''\',
                                pur_business_uid = \'''' + business_id + '''\',
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
                            ]
                response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES"], conn)
                if response[1] == 201:
                    response[0]['payment_id'] = paymentId
                    response[0]['purchase_id'] = purchaseId
                else:
                    if "paymentId" in locals() and "purchaseId" in locals():
                        execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                        execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn)
                return response
            except:
                response = {'message': "Payment process error."}
                return response, 500
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# ---------- ADMIN ENDPOINTS ----------------#
# admin endpoints start from here            #
#--------------------------------------------#

# Endpoint for Create/Edit menu
class Get_Menu (Resource):
    def get(self):
        try:
            conn = connect()
            menu_date = request.args.get('date')

            if menu_date is None:
                query = """
                        SELECT * FROM sf.menu
                        LEFT JOIN sf.meals m
                            ON menu.menu_meal_id = m.meal_uid
                        """
                return simple_get_execute(query, __class__.__name__, conn)
            else:
                query = """
                        SELECT * FROM sf.menu
                        LEFT JOIN sf.meals m
                            ON menu.menu_meal_id = m.meal_uid
                        WHERE menu.menu_date = '""" + str(menu_date) + """';
                        """
                return simple_get_execute(query, __class__.__name__, conn)
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
                    # ADMIN QUERY 2: MEAL OPTIONS
                    SELECT * FROM sf.meals m;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
class Get_Recipes (Resource):
    def get(self):
        try:
            conn = connect()
            meal_uid = request.args['meal_uid']
            query = """
                    # ADMIN QUERY 3: RECIPES
                    SELECT * FROM sf.meals m 
                    LEFT JOIN sf.recipes rec
                        ON rec.recipe_meal_id = m.meal_uid
                    LEFT JOIN sf.ingredients ing
                        ON recipe_ingredient_id = ing.ingredient_uid
                    LEFT JOIN sf.conversion_units cu
                        ON rec.recipe_measure_id = cu.measure_unit_uid
                    WHERE m.meal_uid = '""" + meal_uid + """';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

class Get_New_Ingredient (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    # ADMIN QUERY 4: NEW INGREDIENT
                    SELECT * FROM sf.ingredients ing
                    LEFT JOIN sf.inventory inv
                        ON ing.ingredient_uid = inv.inventory_ingredient_id
                    LEFT JOIN sf.conversion_units cu
                        ON inv.inventory_measure_id = cu.measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

class Get_Ingredients_To_Purchase (Resource):
    def get(self):
        try:
            conn = connect()
            business_uid = request.args['business_uid']
            query = """
                    # ADMIN QUERY 10: INGREDIENTS TO PURCHASE
                    SELECT *,
                        orders_by_date.quantity * rec.recipe_ingredient_qty * cu.conversion_ratio AS ingredient_qty
                    FROM (
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
                                WHERE lpsilpdm.pur_business_uid = '""" + business_uid + """') 
                                AS final_meals
                            JOIN numbers ON char_length(final_selection) - char_length(replace(final_selection, ';', '')) >= n - 1)
                                AS sub
                        GROUP BY menu_date,
                            final_meals_selected)
                        AS orders_by_date
                    LEFT JOIN sf.recipes rec
                        ON orders_by_date.final_meals_selected = rec.recipe_meal_id
                    LEFT JOIN sf.conversion_units cu
                        ON rec.recipe_measure_id = cu.measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)
class Get_Coupon(Resource):
    def get(self):
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
            business_uid = request.args['business_uid']
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
                            WHERE lpsilpdm.pur_business_uid = '""" + business_uid + """') 
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
            business_uid = request.args['business_uid']
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
                            WHERE lpsilpdm.pur_business_uid = '""" + business_uid + """') 
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

# Define API routes
# Customer APIs

#---------------------------- Select Meal plan pages ----------------------------#
#  * The "plans" endpoint accepts only get request with one required parameter.  #
#  It will return all the meal plans in the SUBSCRIPTION_ITEM table. The returned#
#  info contains all meal plans (which is grouped by item's name) and its        #
#  associated details.                                                           #
api.add_resource(Plans, '/api/v2/plans')
#--------------------------------------------------------------------------------#

#---------------------------- Signup/ Login page --------------------------------#
#  * The "signup" endpoint accepts only POST request with appropriate named      #
#  parameters. Please check the documentation for the right format of those named#
#  parameters.                                                                   #
api.add_resource(SignUp, '/api/v2/signup')
#  * The "Login" endpoint accepts only POST request with at least 2 parameters   #
# in its body. The first param is "email" and the second one is either "password"#
# or "refresh_token". We are gonna re-use the token we got from facebook or      #
# google for our site and we'll pick the refresh token because it will not       #
# expire.                                                                        #
api.add_resource(Login, '/api/v2/login')
#--------------------------------------------------------------------------------#

#------------- Checkout, Meal Selection and Meals Schedule pages ----------------#
#  * The "Meals" endpoint only accepts GET request with an optional parameter. It#
# will return the whole available menu info. If the "startDate" param is given.  #
# The returning menu info only contain the menu which starts from that date.     #
# Notice that the optional parameter must go after the slash.
api.add_resource(Meals, '/api/v2/meals', '/api/v2/meals/<string:startDate>')
#  * The "accountsalt" endpoint accepts only GET request with a required param.  #
#  It will return the information of password hashed and password salt for an     #
# associated email account.
api.add_resource(AccountSalt, '/api/v2/accountsalt')
#  * The "accountpurchases" only accepts GET request with 2 required parameters. #
#  It will return the information of all current purchases of a specific customer#
#  of a specific business. Accepting parameters for this endpoints are:          #
#  "customer_uid", "business_uid".                                                 #
api.add_resource(AccountPurchases, '/api/v2/accountpurchases')
#  * The "next_billing_date" only accepts GET request with 1 required parameter. #
#  It will return the information of the next billing date of a specific business#
# The required parameter is: "business_uid
api.add_resource(Next_Billing_Date, '/api/v2/next_billing_date')
#  * The "next_addon_charge" only accepts GET request without any parameter. It  #
# will return the next addon charge information.
api.add_resource(Next_Addon_Charge, '/api/v2/next_addon_charge')
#  * The "selectedmeals" only accepts GET request with two required parameters   #
# "customer_id" and "business_id".It will return the information of all selected #
# meals and addons which are associated with the specific purchase.              #
api.add_resource(Meals_Selected, '/api/v2/meals_selected')
#  * The "Meals_Selection" accepts POST request with appropriate parameters      #
#  Please read the documentation for these parameters and its formats.           #
api.add_resource(Meals_Selection, '/api/v2/meals_selection')
#  * The "checkout" accepts POST request with appropriate parameters. Please read#
# the documentation for these parameters and its formats.                        #
api.add_resource(Checkout, '/api/v2/checkout')
#--------------------------------------------------------------------------------#

#*********************************************************************************#
#*******************************  ADMIN APIs  ************************************#
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
api.add_resource(Get_Recipes, '/api/v2/get_recipes')
api.add_resource(Get_New_Ingredient, '/api/v2/get_new_ingredients')
api.add_resource(Get_Ingredients_To_Purchase, '/api/v2/get_ingredients_to_purchase')
#-------------------------------- Plan / Coupon pages ----------------------------#
#  * The user can access /api/v2/plans endpoint to get all Plans.                 #
#  * The Get_coupon endpoint accepts only GET request with a required argument    #
#  ("business_uid"). This endpoint will returns all active coupons in the COUPON   #
#  table.                                                                         #
api.add_resource(Get_Coupon, '/api/v2/get_coupons')
#  * The Get_Orders_By_Purchase_id endpoint accepts only GET request without any  #
#  parameters. It will return meal orders based on the purchase_uid.               #
api.add_resource(Get_Orders_By_Purchase_Id, '/api/v2/get_orders_by_purchase_id')
#  * The Get_Orders_By_Menu_Date endpoint accepts only GET request without any    #
#  parameters. It will return meal orders based on the menu date.                 #
api.add_resource(Get_Orders_By_Menu_Date, '/api/v2/get_orders_by_menu_date')


#**********************************************************************************#

# Run on below IP address and port
# Make sure port number is unused (i.e. don't use numbers 0-1023)
# lambda function at: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=2000)

