import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="eudr_risk", user="eudr", password="eudr_dev_password"
)
cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone())

cur.execute("SELECT postgis_version();")
print(cur.fetchone())

conn.close()