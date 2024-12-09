from tools import db_utils

print("Test del modulo tools.db_utils")
db_utils.execute_query("SELECT 1")  # Test semplice
print("Test completato!")
