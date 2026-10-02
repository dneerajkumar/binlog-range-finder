#!/usr/bin/env python3
"""
MySQL Environment Detector Module
Provides environment inspection for MySQL deployments (Aurora, RDS, Standalone).
"""

import logging
from typing import Dict, Any, Optional
import pymysql

# Configure logger
logger = logging.getLogger(__name__)


class DatabaseEnvironmentDetector:
    """Detects MySQL deployment context and instance characteristics."""

    def __init__(
        self,
        host: str,
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "information_schema",
        connect_timeout: int = 5,
    ):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.connect_timeout = connect_timeout

    def _get_connection(self) -> pymysql.Connection:
        """Establishes database connection using dict cursor."""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            connect_timeout=self.connect_timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def detect(self) -> Dict[str, Any]:
        """
        Executes environment detection logic.

        Returns:
            Dict containing environment classification and metadata.
        """
        logger.info("Connecting to %s:%d to inspect environment...", self.host, self.port)
        
        try:
            conn = self._get_connection()
        except pymysql.MySQLError as e:
            logger.error("Database connection failed for %s:%d: %s", self.host, self.port, e)
            raise ConnectionError(f"Could not connect to MySQL at {self.host}:{self.port}: {e}") from e

        metadata: Dict[str, Any] = {
            "host": self.host,
            "port": self.port,
        }

        with conn:
            with conn.cursor() as cursor:
                # 1. Check for AWS Aurora
                cursor.execute("SHOW VARIABLES LIKE 'aurora_version';")
                aurora_var = cursor.fetchone()

                if aurora_var and aurora_var.get("Value"):
                    metadata["type"] = "AWS Aurora MySQL"
                    metadata["aurora_version"] = aurora_var["Value"]

                    # Check Writer vs Reader Node status
                    cursor.execute("SHOW VARIABLES LIKE 'innodb_read_only';")
                    read_only = cursor.fetchone()
                    is_read_only = read_only and read_only.get("Value") == "ON"
                    metadata["node_role"] = "Reader Node" if is_read_only else "Writer Node"

                    # Fetch Aurora Server ID
                    cursor.execute("SELECT @@aurora_server_id AS server_id;")
                    server_id = cursor.fetchone()
                    if server_id:
                        metadata["aurora_server_id"] = server_id.get("server_id")

                    return metadata

                # 2. Check for AWS RDS
                cursor.execute(
                    """
                    SELECT ROUTINE_NAME 
                    FROM INFORMATION_SCHEMA.ROUTINES 
                    WHERE ROUTINE_SCHEMA = 'mysql' 
                      AND ROUTINE_NAME LIKE 'rds_%' 
                    LIMIT 1;
                    """
                )
                rds_routine = cursor.fetchone()

                cursor.execute("SELECT user FROM mysql.user WHERE user = 'rdsadmin' LIMIT 1;")
                rds_user = cursor.fetchone()

                if rds_routine or rds_user:
                    metadata["type"] = "AWS RDS MySQL"
                    cursor.execute("SELECT @@version AS version, @@version_comment AS version_comment;")
                    ver_info = cursor.fetchone() or {}
                    metadata["mysql_version"] = ver_info.get("version")
                    metadata["version_comment"] = ver_info.get("version_comment")
                    return metadata

                # 3. Default: Standalone / On-Prem / EC2 MySQL
                metadata["type"] = "Standalone MySQL"
                cursor.execute(
                    "SELECT @@version AS version, @@version_comment AS version_comment, @@hostname AS hostname;"
                )
                ver_info = cursor.fetchone() or {}
                metadata["mysql_version"] = ver_info.get("version")
                metadata["version_comment"] = ver_info.get("version_comment")
                metadata["hostname"] = ver_info.get("hostname")

                return metadata


def detect_environment(
    host: str,
    port: int = 3306,
    user: str = "root",
    password: str = "",
    **kwargs
) -> Dict[str, Any]:
    """Convenience wrapper function for quick module invocation."""
    detector = DatabaseEnvironmentDetector(host=host, port=port, user=user, password=password, **kwargs)
    return detector.detect()
