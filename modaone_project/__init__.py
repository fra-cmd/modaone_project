import pymysql

pymysql.install_as_MySQLdb()

# Agrega el comentario "# type: ignore" al final de esta línea
import MySQLdb  # type: ignore

if hasattr(MySQLdb, 'version_info'):
    MySQLdb.version_info = (2, 2, 1, 'final', 0)
    MySQLdb.__version__ = '2.2.1'