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

stripe_public_key = 'pk_test_6RSoSd9tJgB2fN2hGkEDHCXp00MQdrK3Tw'
stripe_secret_key = 'sk_test_fe99fW2owhFEGTACgW3qaykd006gHUwj1j'
stripe.api_key = stripe_secret_key

RDS_HOST = 'pm-mysqldb.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
RDS_PORT = 3306
RDS_USER = 'admin'
RDS_DB = 'ms'

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
                elif type(row[key]) is date or type(row[key]) is datetime:
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

class SignUp(Resource):
    def post(self):
        response = {}
        items = []
        try:
            conn = connect()
            should_delete = False
            data = request.get_json(force=True)

            Email = data['email'].lower()
            FirstName = data['first_name'].lower()
            LastName = data['last_name'].lower()
            Address = data['address'].lower()
            City = data['city'].lower()
            State = data['state'].lower()
            zip_code = data['zip_code']
            PhoneNumber = data['phone_number']
            WeeklyUpdates = data['weekly_update'].lower()
            Referral = data['referral'].lower()
            Role = data['role']
            registered_by = 'email' if data.get('registered_by') is None else data.get('registered_by').lower()
            if (data.get('registered_by') is not None and registered_by != 'email'):
                AccessToken = data['access_token'].lower()
                RefreshToken = data['refresh_token'].lower()

            # check if there is a same customer_id existing
            query = """
                    SELECT email FROM customers
                    WHERE email = \'""" + Email + "\';"

            emailExists = execute(query, 'get', conn)

            if emailExists['code'] == 280 and len(emailExists['result']) > 0:
                statusCode = 400
                response['message'] = 'Email address is already taken.'
                return response, statusCode

            get_user_id_query = "CALL get_new_customer_id;"
            NewUserIDresponse = execute(get_user_id_query, 'get', conn)
            if NewUserIDresponse['code'] == 490:
                print("Cannot get new User id")
                response['message'] = "Internal Server Error."
                return response, 500
            NewUserID = NewUserIDresponse['result'][0]['new_id']

            if registered_by == 'email':
                salt = getNow()
                hashed = sha512((data['password'] + salt).encode()).hexdigest()
            # write everything to database

            customer_insert_query = """INSERT INTO customers
                                (
                                    customer_id,
                                    first_name,
                                    last_name,
                                    phone_num,
                                    email,
                                    address,
                                    city,
                                    state,
                                    zip_code,
                                    registered_by,
                                    referral_source,
                                    role,
                                    created_at,
                                    updated_at,
                                    weekly_updates
                                )
                            VALUES
                            ('""" + NewUserID + """',
                            '""" + FirstName + """',
                            '""" + LastName + """',
                            '""" + PhoneNumber + """',
                            '""" + Email + """',
                            '""" + Address + """',
                            '""" + City + """',
                            '""" + State + """',
                            '""" + zip_code + """',
                            '""" + registered_by + """',
                            '""" + Referral + """',
                            '""" + Role + """',
                            '""" + getToday() + """',
                            '""" + getToday() + """',
                            '""" + WeeklyUpdates + """');"""

            usnInsert = execute(customer_insert_query, 'post', conn)
            should_delete = True  #this is used for error handle
            if usnInsert['code'] != 281:
                statusCode = 500
                response['message'] = 'Internal server error.'
                return response, statusCode
            if registered_by =='email':
                password_update_query = """
                    UPDATE customers SET
                        password_salt = '""" + salt + """',
                        password_hashed = '""" + hashed + """',
                        password_algorithm = 'SHA512',
                        email_verified = '0'
                    WHERE customer_id = '""" + NewUserID + """';"""
                password_update = execute(password_update_query, 'post', conn)
                if password_update['code'] != 281:
                    execute("""DELETE FROM customers WHERE customer_id = '""" + NewUserID + """';""", 'post', conn)
                    response['message'] = "Internal Server Error."
                    return response, 500
                    # Sending verification email
                token = s.dumps(Email)

                msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[Email])
                print(hashed)
                link = url_for('confirm', token=token, hashed=hashed, _external=True)

                msg.body = "Click on the link {} to verify your email address.".format(link)

                mail.send(msg)

            response['message'] = "OK"
            response['first_name'] = FirstName
            response['customer_id'] = NewUserID

            return response, 200
        except:
            print("Error happened while Sign Up")
            if should_delete:
                execute("""DELETE FROM customers WHERE customer_id = '""" + NewUserID + """';""", 'post', conn)
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
class AccountSalt(Resource):
    def get(self, accEmail):
        response = {}
        try:
            conn = connect()

            items = execute(""" SELECT password_hashed, password_salt 
                                    FROM customers cus
                                    WHERE customer_email = \'""" + accEmail + """\';""", 'get', conn)
            if items['code'] != 280:
                response['message'] = "Internal Server Error."
                return response, 500
            if not items['result']:
                response['message'] = "User's password not found."
                return response, 404
            response['message'] = 'Request successful.'
            response['result'] = items['result']
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Login(Resource):

    def post(self, accEmail, accPass):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print(data)
            if data.get('ip_address') == None:
                response['message'] = 'Request failed, did not receive IP address.'
                return response, 400
            if data.get('browser_type') == None:
                response['message'] = 'Request failed, did not receive browser type.'
                return response, 400

            queries = [
                """ SELECT
                        user_uid,
                        first_name,
                        last_name,
                        user_email,
                        phone_number,
                        create_date,
                        last_update,
                        referral_source,
                        email_verify
                    FROM ptyd_accounts""" +
                "\nWHERE user_email = " + "\'" + accEmail + "\';"]

            items = execute(queries[0], 'get', conn)
            user_uid = items['result'][0]['user_uid']

            queries.append(
                "SELECT * FROM ptyd_passwords WHERE password_user_uid = \'" + user_uid + "\';")
            password_response = execute(queries[1], 'get', conn)
            if accPass == password_response['result'][0]['password_hash']:
                print("Successful authentication.")
                response['message'] = 'Request successful.'
                response['result'] = items
                response['auth_success'] = True
                httpCode = 200
            else:
                print("Wrong password.")
                response['message'] = 'Request failed, wrong password.'
                response['auth_success'] = False
                httpCode = 401

            login_attempt = {
                'user_uid': user_uid,
                'attempt_hash': accPass,
                'ip_address': data['ip_address'],
                'browser_type': data['browser_type'],
            }

            if response['auth_success']:
                login_attempt['auth_success'] = 'TRUE'
            else:
                login_attempt['auth_success'] = 'FALSE'

            response['login_attempt_log'] = LogLoginAttempt(
                login_attempt, conn)

            return response, httpCode
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
            #           rowDict['meal_photo_url'] = 'https://prep-to-your-door-s3.s3.us-west-1.amazonaws.com/dev_imgs/700-000014.png'

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
                    related_price = eachMeal['extra_meal_price']
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
                            extra_meal_price,
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
                            extra_meal_price,
                            meal_calories,
                            meal_protein,
                            meal_carbs,
                            meal_fiber,
                            meal_sugar,
                            meal_fat,
                            meal_sat
                        FROM ms.menu
                        LEFT JOIN ms.meals ON ms.menu.menu_meal_id = ms.meals.meal_id
                        WHERE (menu_category = 'SEAS_FAVE_1' OR menu_category = 'SEAS_FAVE_2' OR menu_category = 'SEAS_FAVE_3')
                        AND menu_date = '""" + date['menu_date'] + "';", 'get', conn)

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
                            extra_meal_price,
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
                            extra_meal_price,
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

                    thursday = stamp - timedelta(days=2)

                    today = datetime.now()

                    if today < thursday:
                        # stamp = stamp + timedelta(days=7)

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
        response = {}
        items = {}
        try:
            conn = connect()
            queries = """SELECT * FROM subscription_items subi
                            WHERE payment_frequency = "4 Week Pre-Pay"
                            GROUP BY item_name
                            ORDER BY num_items ASC;"""

            items['MealPlans'] = execute(queries, 'get', conn)

            if items['MealPlans']['code'] != 280:
                response['message'] = "Internal Server Error."
                return response, 500
            items['MealPlans'] =  items['MealPlans']['result']
            all_plans = execute("""SELECT * FROM subscription_items subi;""", 'get', conn)
            if all_plans['code'] != 280:
                response['message'] = "Internal Server Error."
                return response, 500
            all_plans = all_plans['result']

            for plan in all_plans:
                if plan['item_name'] is not None:
                    if items.get(plan['item_name']) is None:
                        items[plan['item_name']] = [plan]
                    else:
                        items[plan['item_name']] += [plan]
            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class AccountPurchases(Resource):
    # HTTP method GET
    def get(self, customer_id):
        response = {}

        try:
            start_date = request.args.get('startdate')

            if start_date is not None:
                startDate = datetime.strptime(start_date, "%Y%m%d")
                now = startDate
            else:
                now = date.today()

        except:
            raise BadRequest('Request failed, bad startDate parameter.')

        try:
            conn = connect()

            dayOfWeek = now.weekday()
            # Get the soonest Saturday, same day if today is Saturday
            sat = now + timedelta(days=(12 - dayOfWeek) % 7)
            thur = now + timedelta(days=(10 - dayOfWeek) % 7)

            print("sat before: ", sat)
            print("thur before: ", thur)

            # If today is Thursday after 4PM
            # if sat == now and now.hour >= 16:
            #     sat += timedelta(days=7)

            # if thursday is passed, the affected week is the next week
            # if now + timedelta(days=7) > thur:
            # #     thur += timedelta(days=7)
            #     sat += timedelta(days=7)
            # change sat into string
            sat = sat.strftime("%Y-%m-%d")
            thur = thur.strftime("%Y-%m-%d")
            print("sat after: ", sat)
            print("thur after: ", thur)
            queries = ["""
                SELECT 
                    pay.payment_id 
                    ,pur.customer_id
                    ,pay.coupon_id
                    ,pay.gift
                    ,(pay.amount_due + IFNULL(addon.total_charge,0)) AS amount_due
                    ,pay.amount_paid
                    ,pur.purchase_id AS purchase_id
                    ,pay.payment_timestamp AS last_payment_timestamp
                    -- ,pay.payment_type
                    ,pay.cc_num
                    ,pay.cc_expired_date
                    ,pay.cc_cvv
                    -- ,pay.billing_zip
                    ,pur.meal_plan_id
                    ,plans.MaximumMeals
                    ,plans.meal_plan_desc
                    ,plans.meal_plan_price
                    ,plans.payment_frequency
                    ,pur.start_date AS delivery_start_date -- should calculate to become saturday
                    ,pur.delivery_first_name
                    ,pur.delivery_last_name
                    ,pur.delivery_email
                    ,pur.delivery_phone_num
                    ,pur.delivery_address
                    -- ,purch.delivery_address_unit
                    ,pur.delivery_city
                    ,pur.delivery_state
                    ,pur.delivery_zip_code
                    -- ,pur.delivery_region
                    ,pur.delivery_instructions
                    ,pur.weeks_remaining AS paid_weeks_remaining
                    -- ,snap.next_billing_date AS next_charge_date
                    , "2020-08-06" AS next_charge_date -- determine by program
                    ,IFNULL(addon.total_charge, 0.00) AS total_charge
                    ,pay.amount_due AS amount_due_before_addon
                    ,pur.start_date
                    ,pur.weeks_remaining
                 , \'""" + thur + """\' AS next_addon_charge_date
                FROM (
                -- purchases query , checks to make sure the account is active 
                SELECT 
                    A.purchase_id
                    ,A.customer_id
                    ,A.meal_plan_id
                    ,A.start_date
                    ,A.delivery_first_name
                    ,A.delivery_last_name
                    ,A.delivery_email
                    ,A.delivery_phone_num
                    ,A.delivery_address
                    -- ,A.delivery_address_unit
                    ,A.delivery_city
                    ,A.delivery_state
                    ,A.delivery_zip_code
                    ,A.weeks_remaining
                    -- ,A.delivery_region
                    ,A.delivery_instructions
                    ,A.purchase_status
                FROM ms.purchases A
                WHERE
                    purchase_status = "ACTIVE"
                ) pur
                JOIN (
                -- payments query
                    SELECT
                        _ms.purchase_id  AS payment_purchase_id
                        ,_ms.payment_id
                        , p2.customer_id
                        ,_ms.payment_timestamp
                        ,_ms.coupon_id 
                        ,_ms.gift
                        ,_ms.amount_due
                        ,_ms.amount_paid
                        ,_ms.purchase_id
                        -- ,ms3.payment_type
                        ,CONCAT('XXXXXXXXXXXX', right(_ms.cc_num,4)) AS cc_num
                        ,_ms.cc_expired_date
                        ,_ms.cc_cvv
                        -- ,ms3.billing_zip
                    FROM
                        ms.payments _ms 
                    JOIN (
                    SELECT customer_id, purchase_id FROM ms.purchases) p2
                    ON _ms.purchase_id = p2.purchase_id
                    INNER JOIN (
                        SELECT
                            B.purchase_id,
                            B.payment_id,
                            MAX(B.payment_timestamp) AS latest_payment
                            FROM ms.payments B
                            GROUP BY B.purchase_id
                        ) ms4 ON _ms.purchase_id = ms4.purchase_id AND payment_timestamp = latest_payment
                ) pay 
                ON pur.purchase_id = pay.purchase_id
                JOIN (
                -- meal plan query
                SELECT 
                    B.meal_plan_id
                    ,B.num_meals AS MaximumMeals
                    ,B.meal_plan_desc
                    ,B.payment_frequency
                    ,B.meal_plan_price
                FROM 
                    ms.meal_plans B
                ) plans
                ON pur.meal_plan_id = plans.meal_plan_id
                LEFT JOIN (
                -- ADDON query
                        SELECT
                            purchase_id,
                            week_affected,
                            SUM(total) AS total_addons,
                            SUM(charge) AS total_charge
                        FROM ( # QUERY 11
                            SELECT purchase_id
                                , week_affected
                                , meal_selected
                                , meal_name
                                , COUNT(num) as total
                                , extra_meal_price
                                , COUNT(num) * extra_meal_price as charge
                            FROM (
                                SELECT *
                                    , substring_index(substring_index(meal_selection,';',n),';',-1) AS meal_selected
                                    , n AS num
                                FROM (# QUERY 1
                                   SELECT
                                        ms1.purchase_id
                                        -- ,ms2.purchase_id
                                        , ms1.week_affected
                                        -- , ms2.week_affected
                                        , "0" AS num_meals
                                        , "0" AS delivery_day
                                        , ms1.meal_selection
                                        -- , ms1.selection_time
                                        -- , ms2.latest_selection
                                        -- , ms1.delivery_day
                                    FROM ms.addons_selected AS ms1
                                    INNER JOIN (
                                        SELECT
                                            purchase_id
                                            , week_affected
                                            , meal_selection
                                            , MAX(selection_time) AS latest_selection
                                            -- , delivery_day
                                        FROM ms.addons_selected
                                        GROUP BY purchase_id
                                            , week_affected
                                    ) as ms2 
                                    ON ms1.purchase_id = ms2.purchase_id 
                                        AND ms1.week_affected = ms2.week_affected 
                                        AND ms1.selection_time = ms2.latest_selection
                                    ORDER BY purchase_id
                                        , week_affected)
                                        AS combined
                                    JOIN numbers ON char_length(meal_selection) - char_length(replace(meal_selection, ';', '')) >= n - 1)
                                AS sub
                            LEFT JOIN ms.meals meals ON sub.meal_selected = meals.meal_id
                            GROUP BY purchase_id
                                , week_affected
                                , meal_selected
                            ORDER BY purchase_id
                                , week_affected
                                , num_meals
                                , meal_selected)
                            AS addons
                        WHERE week_affected = \'""" + sat + """\'
                        GROUP BY purchase_id,
                            week_affected
                ) addon
                ON pur.purchase_id = addon.purchase_id
                WHERE pur.customer_id = '""" + customer_id + """'
                GROUP BY pay.payment_id;""",
                       "   SELECT * FROM monday_zipcodes;"]

            items = execute(queries[0], 'get', conn)
            print(items)
            mondayZipsQuery = execute(queries[1], 'get', conn)
            print(mondayZipsQuery)
            mondayZips = []
            for eachZip in mondayZipsQuery['result']:
                mondayZips.append(eachZip['zipcode'])
            print(mondayZips)

            del mondayZipsQuery

            for eachItem in items['result']:
                # last_charge_date = datetime.strptime(eachItem['last_payment_time_stamp'], '%Y-%m-%d %H:%M:%S')
                # next_charge_date = None

                # if eachItem['payment_frequency'] == 'Weekly':
                #     next_charge_date = last_charge_date + timedelta(days=7)
                # elif eachItem['payment_frequency'] == 'Bi-Weekly':
                #     next_charge_date = last_charge_date + timedelta(days=14)
                # elif eachItem['payment_frequency'] == 'Monthly':
                #     next_charge_date = last_charge_date + timedelta(days=28)

                # eachItem['paid_weeks_remaining'] = str(int((next_charge_date - datetime.now()).days / 7) + 1)
                # eachItem['next_charge_date'] = str(next_charge_date.date())

                if eachItem['delivery_zip_code'] in mondayZips:
                    eachItem['monday_available'] = True
                else:
                    eachItem['monday_available'] = False

            response['message'] = 'Request successful.'
            response['result'] = items['result']
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
# Bing API - start
class Coordinates:
    # array of addresses such as
    # ['Dunning Ln, Austin, TX 78746', '12916 Cardinal Flower Drive, Austin, TX 78739', '51 Rainey St., austin, TX 78701']
    def __init__(self, locations):
        self.locations = locations

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
            print(type(i["latitude"]))

        # return array of dictionaries containing lat, long points
        return coordinates

    # returns an address formatted to be used for the Bing API to get locations
    def formatAddress(self, address):
        output = address.replace(" ", "%20")
        if "." in output:
            output = output.replace(".", "")
        return output

class Checkout(Resource):
    def getDates(self, frequency):
        dates = {}
        dayOfWeek = date.today().weekday()

        # Get the soonest Thursday, same day if today is Thursday
        thurs = date.today() + timedelta(days=(3 - dayOfWeek) % 7)

        # If today is Thursday after 4PM
        if thurs == date.today() and datetime.now().hour >= 16:
            thurs += timedelta(days=7)

        # Set start date to Saturday after thurs
        #       dates['startDate'] = thurs + timedelta(days=2)
        dates['startDate'] = (thurs + timedelta(days=2)).strftime("%Y-%m-%d")

        # Set end date to 1st/2nd/4th Monday after thurs
        # Set next billing date to Friday after the end date
        if frequency == 'Weekly':
            dates['endDate'] = (thurs + timedelta(days=4)).strftime("%Y-%m-%d")
            dates['billingDate'] = (
                    thurs + timedelta(days=7)).strftime("%Y-%m-%d")
            dates['weeksRemaining'] = '1'
        elif frequency == '2 Week Pre-Pay':
            dates['endDate'] = (thurs + timedelta(days=11)
                                ).strftime("%Y-%m-%d")
            dates['billingDate'] = (
                    thurs + timedelta(days=14)).strftime("%Y-%m-%d")
            dates['weeksRemaining'] = '2'
        elif frequency == '4 Week Pre-Pay':
            dates['endDate'] = (thurs + timedelta(days=25)
                                ).strftime("%Y-%m-%d")
            dates['billingDate'] = (
                    thurs + timedelta(days=28)).strftime("%Y-%m-%d")
            dates['weeksRemaining'] = '4'

        return dates

    def getPaymentQuery(self, data, couponID, paymentId, stripe_chargeID, purchaseId):

        stripe_charge_id = "'" + stripe_chargeID + "'"  if stripe_chargeID is not None else 'NULL'

        couponID = 'NULL' if couponID is None or couponID == "" else "'" + couponID + "'"

        amount_due = round(float(data['total_charge']) + float(data['total_discount']), 2)

        query = """ INSERT INTO payments
                    (
                        payment_id,
                        purchase_id,
                        start_delivery_date,
                        recurring,
                        gift,
                        coupon_id,
                        amount_due,
                        amount_discount,
                        amount_paid,
                        payment_timestamp,
                        payment_type,
                        stripe_charge_id,
                        cc_num,
                        cc_expired_date,
                        cc_cvv,
                        cc_billing_zip,
                        isAddon
                    )
                    VALUES (
                        \'""" + paymentId + """\',
                        \'""" + purchaseId + """\',
                        \'""" + data['start_delivery_date'] + """\',
                        \'TRUE\',
                        \'""" + str(data['is_gift']).upper() + """\',
                        """ + couponID + """,
                        \'""" + str(amount_due) + """\',
                        \'""" + str(round(float(data['total_discount']),2)) + """\',
                        \'""" + str(round(float(data['total_charge']),2)) + """\',
                        \'""" + getNow() + """\',
                        'STRIPE',
                        """ + stripe_charge_id + """,
                        \'""" + data['cc_num'] + """\',
                        \'""" + data['cc_exp_year'] + "-" + data['cc_exp_month'] + """-01\',
                        \'""" + data['cc_cvv'] + """\',
                        \'""" + data['billing_zip'] + """\',
                        'FALSE');"""
        return query



    def post(self):
        response = {}
        reply = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("Received:", data)

            if data['delivery_address_unit'] == None or data['delivery_address_unit'] == "":
                data['delivery_address_unit'] = 'NULL'
            else:
                data['delivery_address_unit'] = '\'' + data['delivery_address_unit'] + '\''


            def get_new_paymentID():
                newPaymentQuery = execute(
                    "CALL get_new_payment_id", 'get', conn)
                if newPaymentQuery['code'] == 280:
                    return newPaymentQuery['result'][0]['new_id']
                return "Could not generate new payment ID", 500
            def get_new_purchaseID():
                newPurchaseQuery = execute(
                    "CALL get_new_purchase_id", 'get', conn)
                if newPurchaseQuery['code'] == 280:
                    return newPurchaseQuery['result'][0]['new_id']
                return "Could not generate new purchase ID", 500

            purchaseId = get_new_purchaseID()
            if purchaseId[1] == 500:
                return purchaseId
            paymentId = get_new_paymentID()
            if paymentId[1] == 500:
                return paymentId

            mealPlan = data['item'].split(' Subscription')[0]

            queries = ["""
                SELECT
                    subscription_id
                    , payment_frequency
                FROM
                    subscriptions
                WHERE
                    subscription_desc = \'""" + mealPlan + "\'", """
                SELECT
                    cc_num
                FROM
                    payments pay, purchases pur
                WHERE
                    pay.purchase_id = pur.purchase_id
                    AND customer_id = \'""" + data['user_id'] + "\';"]


            # User authenticated
            # check the customer_id and see what kind of registration.
            # if it was registered by email then check the password.
            customer_query = """SELECT * FROM customers WHERE customer_id = '""" + data['user_id'] + """';"""
            customer_res = execute( customer_query, 'get', conn)

            if customer_res['code'] != 280 or not customer_res['result']:
                response['message'] = "Could not authenticate user"
                return response, 401
            if customer_res['result'][0]['registered_by'] == "email":
                if customer_res['result'][0]['password_hashed'] != data['salt']:
                    response['message'] = "Could not authenticate user. Wrong Password"
                    return response, 401
            mealPlanQuery = execute(queries[0], 'get', conn)

            if mealPlanQuery['code'] == 280:
                print("Getting meal plan ID...")
                print(mealPlanQuery)
                mealPlanId = mealPlanQuery['result'][0]['subscription_id']
                dates = self.getDates(
                    mealPlanQuery['result'][0]['payment_frequency'])
                print("Meal Plan ID:", mealPlanId)
                print()
                data['start_delivery_date'] = (datetime.strptime(dates['startDate'], "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
            else:
                response['message'] = 'Could not retrieve meal ID of requested plan.'
                response['error'] = mealPlanQuery
                print("Error:", response['message'])
                print("Error JSON:", response['error'])
                return response, 501

            # replace with real longitute and latitude
            addressObj = Coordinates([data['delivery_address']])
            delivery_coord = addressObj.calculateFromLocations()[0]

            # If a key of the coordinates object is None, set to NULL
            # Otherwise wrap quotation marks around it
            # This is because delivery_lat and delivery_long are VARCHAR in db
            for key in delivery_coord:
                if delivery_coord[key] == None:
                    delivery_coord[key] = 'NULL'
                else:
                    delivery_coord[key] = '\'' + \
                                          str(delivery_coord[key]) + '\''
            purchase_query = """ INSERT INTO purchases
                    (
                        purchase_timestamp,
                        purchase_id,
                        purchase_status,
                        customer_id,
                        subscription_id,
                        delivery_first_name,
                        delivery_last_name,
                        delivery_phone_num,
                        delivery_email,
                        delivery_address,
                        delivery_address_unit,
                        delivery_city,
                        delivery_state,
                        delivery_zip_code,
                        delivery_long,
                        delivery_lat,
                        delivery_instructions
                    )
                    VALUES
                    (
                        \'""" + str(getNow()) + """\',
                        \'""" + str(purchaseId) + """\',
                        \'ACTIVE\',
                        \'""" + str(data['user_id']) + """\',
                        \'""" + str(mealPlanId) + """\',
                        \'""" + str(data['delivery_first_name']) + """\',
                        \'""" + str(data['delivery_last_name']) + """\',
                        \'""" + str(data['delivery_phone']) + """\',
                        \'""" + str(data['delivery_email']) + """\',
                        \'""" + str(data['delivery_address']) + """\',
                        """ + str(data['delivery_address_unit']) + """,
                        \'""" + str(data['delivery_city']) + """\',
                        \'""" + str(data['delivery_state']) + """\',
                        \'""" + str(data['delivery_zip']) + """\',
                        """ + str(delivery_coord['longitude']) + """,
                        """ + str(delivery_coord['latitude']) + """,
                        \'""" + str(data['delivery_instructions']) + """\');"""

            # Validate credit card
            if data['cc_num'][0:12] == "XXXXXXXXXXXX":
                last_four_digits = data['cc_num'][12:]

                select_card_query = """SELECT cc_num FROM (SELECT p2.* FROM payments p2, purchases pur
                                                WHERE pur.purchase_id = p2.purchase_id
                                                AND pur.customer_id = '""" + data['user_id'] + """'
                                                AND RIGHT(cc_num, 4) = '""" + last_four_digits + """'
                                                AND cc_expired_date = '""" + data['cc_exp_year'] + "-" + data['cc_exp_month'] + """-01'
                                                AND cc_cvv = '""" + data['cc_cvv'] + """') AS p
                                        WHERE payment_timestamp = (SELECT MAX(payment_timestamp) FROM payments p2, purchases pur
                                                                        WHERE pur.purchase_id = p2.purchase_id
                                                                        AND pur.customer_id = '""" + data['user_id'] + """'
                                                                        AND RIGHT(cc_num, 4) = '""" + last_four_digits + """'
                                                                        AND cc_expired_date = '""" + data['cc_exp_year'] + "-" + data['cc_exp_month'] + """-01'
                                                                        AND cc_cvv = '""" + data['cc_cvv'] + """')
                                        AND cc_num IS NOT NULL;"""

                card_selected = execute(select_card_query, 'get', conn)
                if not card_selected['result']:
                    response['message'] = "Credit card info is incorrect."
                    return response, 400
                # update data['cc_num'] to write to database
                data['cc_num'] = card_selected['result'][0].get('cc_num')

            #checking for coupon and preparing for stripe charge

            coupon_id = data.get('coupon_id')
            if coupon_id == "" or coupon_id is None:
                charge = round(float(data['total_charge']),2)
            else:
                charge = round(float(data['total_charge']) - float(data['total_discount']), 2)
            # create a stripe charge and make sure that charge is successful before writing it into database
            # we should use Idempotent key to prevent sending multiple payment requests due to connection fail.
            try:
                #create a token for stripe
                card_dict = {"number": data['cc_num'], "exp_month": int(data['cc_exp_month']),"exp_year": int(data['cc_exp_year']),"cvc": data['cc_cvv']}

                try:
                    card_token = stripe.Token.create(card=card_dict)
                    stripe_charge = stripe.Charge.create(
                        amount=int(round(charge*100, 0)),
                        currency="usd",
                        source=card_token,
                        description="Charge customer %s for %s" %(data['delivery_first_name'] + " " + data['delivery_last_name'], data['item']),)
                except stripe.error.CardError as e:
                    # Since it's a decline, stripe.error.CardError will be caught
                    response['message'] = e.error.message
                    return response, 400

                if str(coupon_id) != "" and coupon_id is not None:
                    # update coupon table
                    coupon_id = "'" + coupon_id + "'"
                    coupon_query = """UPDATE coupons SET num_used = num_used + 1
                                WHERE coupon_id =  """ + str(coupon_id) + ";"
                    res = execute(coupon_query, 'post', conn)

                payment_query = self.getPaymentQuery(data, coupon_id, paymentId, stripe_charge.get('id'), purchaseId)

                reply['payment'] = execute(payment_query, 'post', conn)

                if reply['payment']['code'] != 281:
                    response['message'] = "Internal Server Error"
                    return response, 500
                print(purchase_query)
                reply['purchase'] = execute(purchase_query, 'post', conn)
                print(reply['purchase'])
                if reply['purchase']['code'] != 281:
                    response['message'] = "Internal Server Error"
                    return response, 500

                response['message'] = 'Request successful.'
                response['result'] = reply
                return response, 200
            except:
                response['message'] = "Payment process error."
                return response, 500
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
            print(data)
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
api.add_resource(Meals, '/api/v2/meals', '/api/v2/meals/<string:startDate>')
api.add_resource(Plans, '/api/v2/plans')
api.add_resource(SignUp, '/api/v2/signup')
api.add_resource(AccountSalt, '/api/v2/accountsalt/<string:accEmail>')
api.add_resource(AccountPurchases, '/api/v2/accountpurchases/<string:customer_id>')
api.add_resource(Checkout, '/api/v2/checkout')

# Admin APIs
api.add_resource(Add_New_Ingredient, '/api/v2/Add_New_Ingredient')
api.add_resource(All_Payments, '/api/v2/All_Payments/<string:user_id>')
api.add_resource(DisplaySaturdays, '/api/v2/saturdays')
api.add_resource(Get_All_Units, '/api/v2/GetUnits')
api.add_resource(Latest_activity, '/api/v2/Latest_activity/<string:user_id>')
api.add_resource(MealCreation, '/api/v2/mealcreation')
api.add_resource(All_Ingredients, '/api/v2/All_Ingredients')
api.add_resource(All_Meals, '/api/v2/All_Meals')
api.add_resource(SavePurchaseNote,'/api/v2/SavePurchaseNote/<string:purchase_id>')
# Run on below IP address and port
# Make sure port number is unused (i.e. don't use numbers 0-1023)
# lambda function: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=2000)

