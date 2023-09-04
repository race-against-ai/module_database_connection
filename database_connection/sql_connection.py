import psycopg2

user = "root_user"
password = "&Cr&X{H[VB*RwP6V"
server = "ngitl-usersession.postgres.database.azure.com"
port = 5432
# database = "ngitl-usersession-nicknames"
database = ""

try:
    conn = psycopg2.connect(user="", password=password, host="ngitl-usersession.postgres.database.azure.com", port=5432, database="")
    cursor = conn.cursor()
    print("connected successfully")

except psycopg2.Error as e:
    print(f"Error connecting to database: {e}")
