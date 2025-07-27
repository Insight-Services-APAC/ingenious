import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict

import matplotlib.pyplot as plt  # type: ignore
import pandas as pd
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

import ingenious.config.config as ingen_config
from ingenious.core.structured_logging import get_logger
from ingenious.utils.load_sample_data import sqlite_sample_db

logger = get_logger(__name__)

_config = ingen_config.get_config()

# Initialize pyodbc as None first
pyodbc = None

# Only import pyodbc if we're using Azure SQL
if _config.azure_sql_services and _config.azure_sql_services.database_name != "skip":
    try:
        import pyodbc  # type: ignore
    except ImportError as e:
        logger.warning(
            "pyodbc not available for Azure SQL connections",
            error=str(e),
            operation="pyodbc_import",
        )
        pyodbc = None


class ToolFunctions:
    @staticmethod
    def aisearch(search_query: str, index_name: str) -> str:
        if not _config.azure_search_services or not _config.azure_search_services[0].endpoint:
            raise ValueError("Azure Search service is not configured")
            
        search_config = _config.azure_search_services[0]
        
        # Choose authentication method based on configuration
        if search_config.use_managed_identity:
            credential = DefaultAzureCredential()
            logger.debug("Using managed identity for Azure Search authentication")
        else:
            if not search_config.key:
                raise ValueError("Azure Search API key is required when not using managed identity")
            credential = AzureKeyCredential(search_config.key)
            logger.debug("Using API key for Azure Search authentication")
            
        client = SearchClient(
            endpoint=search_config.endpoint,
            index_name=index_name,
            credential=credential,
        )
        results = client.search(
            search_text=search_query,
            top=5,
            query_type="semantic",  # semantic, full or simple
            query_answer="extractive",
            query_caption="extractive",
            vector_queries=None,
        )  # vector_queries can input the query as a vector
        text_results = ""
        for result in results:
            captions = result["@search.captions"]
            for caption in captions:
                text_results = text_results + "; " + caption.text
                # if "title" in result:
                #     title = result["title"]
                # else:
                #     title = ""
        return text_results

    @staticmethod
    def update_memory(context: str) -> None:
        """
        Update memory using the MemoryManager for cloud storage support.
        """
        try:
            from ingenious.services.memory_manager import (
                get_memory_manager,
                run_async_memory_operation,
            )

            memory_manager = get_memory_manager(_config)
            run_async_memory_operation(memory_manager.write_memory(context))
        except Exception as e:
            # Fallback to legacy file I/O
            logger.warning(
                "Failed to use MemoryManager, falling back to local file I/O",
                error=str(e),
                memory_path=_config.chat_history.memory_path,
                operation="memory_manager_fallback",
            )
            memory_path = _config.chat_history.memory_path
            with open(f"{memory_path}/context.md", "w") as memory_file:
                memory_file.write(context)


class PandasExecutor:
    @staticmethod
    def plot_bar_chart(data: Dict[str, int]) -> str:
        """
        Generate a bar chart from a dictionary input.

        Parameters:
        data (Dict[str, int]): A dictionary where keys are categories and values are quantities.

        Example:
        plot_bar_chart({"GROUP_A": 518, "GROUP_B": 100})
        """
        # Convert the dictionary to a DataFrame for easier plotting
        df = pd.DataFrame(list(data.items()), columns=["Category", "Value"])

        # Plotting
        plt.figure(figsize=(8, 6))
        plt.bar(df["Category"], df["Value"])
        plt.xlabel("Category")
        plt.ylabel("Value")
        plt.title("Bar Chart")
        plt.show()

        # Save the plot to a temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        plt.savefig(temp_file.name)
        plt.close()  # Close the figure to release memory
        return temp_file.name


# SQL Tools TODO: need a better way to wrap these functions
def get_conn(_config):
    if pyodbc is None:
        raise ImportError(
            "pyodbc is required for Azure SQL connections but is not available"
        )
    connection_string = _config.azure_sql_services.database_connection_string
    # credential = identity.DefaultAzureCredential(exclude_interactive_browser_credential=False)
    # token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("UTF-16-LE")
    # token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    # SQL_COPT_SS_ACCESS_TOKEN = 1256  # This connection option is defined by microsoft in msodbcsql.h
    if not hasattr(pyodbc, "connect"):
        raise ImportError("pyodbc module is not properly imported")
    conn = pyodbc.connect(connection_string)
    cursor = conn.cursor()
    return conn, cursor


# Initialize database connections based on configuration
test_db = None
conn = None
cursor = None

# Check if we should use SQLite (when Azure SQL is disabled)
if not _config.azure_sql_services or _config.azure_sql_services.database_name == "skip":
    print("Initializing SQLite database for local SQL operations...")
    test_db = sqlite_sample_db()  # this is for local sql initialisation
    print("SQLite database initialized successfully")
else:
    # Azure SQL mode
    if pyodbc is not None and _config.azure_sql_services:
        try:
            conn, cursor = get_conn(_config)
            logger.info(
                "Azure SQL connection established",
                operation="azure_sql_connection_success",
            )
        except Exception as e:
            logger.warning(
                "Failed to connect to Azure SQL",
                error=str(e),
                operation="azure_sql_connection",
            )
            conn = None
            cursor = None
    else:
        logger.warning(
            "Azure SQL configured but pyodbc not available",
            operation="azure_sql_missing_pyodbc",
        )


class SQL_ToolFunctions:
    @staticmethod
    def get_db_attr(_config):
        if (
            not _config.azure_sql_services
            or _config.azure_sql_services.database_name == "skip"
        ):
            table_name = _config.local_sql_db.sample_database_name
            # Validate table name to prevent SQL injection
            if not table_name.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"Invalid table name: {table_name}")
            result = test_db.execute_sql(f"""SELECT * FROM "{table_name}" LIMIT 1""")
            column_names = [key for key in result[0]]
            return table_name, column_names
        else:
            database_name = _config.azure_sql_services.database_name
            table_name = _config.azure_sql_services.table_name
            # Validate table name to prevent SQL injection
            if not table_name.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"Invalid table name: {table_name}")
            if cursor is not None:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = ?
                """,
                    (table_name,),
                )
                column_names = [row[0] for row in cursor.fetchall()]
            else:
                # Fallback - create temporary connection
                conn_temp, cursor_temp = get_conn(_config)
                cursor_temp.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = ?
                """,
                    (table_name,),
                )
                column_names = [row[0] for row in cursor_temp.fetchall()]
                conn_temp.close()
            return database_name, table_name, column_names

    @staticmethod
    def get_azure_db_attr(_config):
        if not _config.azure_sql_services:
            raise ValueError("Azure SQL services not configured")
        database_name = _config.azure_sql_services.database_name
        table_name = _config.azure_sql_services.table_name

        # Validate table name to prevent SQL injection
        if not table_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid table name: {table_name}")
        # Get connection if needed
        if cursor is not None:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
            """,
                (table_name,),
            )
            column_names = [row[0] for row in cursor.fetchall()]
        else:
            # Fallback - create temporary connection
            conn_temp, cursor_temp = get_conn(_config)
            cursor_temp.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
            """,
                (table_name,),
            )
            column_names = [row[0] for row in cursor_temp.fetchall()]
            conn_temp.close()
        return database_name, table_name, column_names

    @staticmethod
    def execute_sql_local(
        sql: str,
        timeout: int = 10,  # Timeout in seconds
    ) -> str:
        global test_db
        # Ensure test_db is initialized
        if test_db is None:
            logger.error(
                "test_db is None, attempting to re-initialize",
                operation="sqlite_db_reinit",
            )
            try:
                test_db = sqlite_sample_db()
                logger.info(
                    "Successfully re-initialized test_db",
                    operation="sqlite_db_reinit_success",
                )
            except Exception as e:
                error_msg = f"Failed to initialize SQLite database: {e}"
                logger.error(
                    "Failed to initialize SQLite database",
                    error=str(e),
                    operation="sqlite_db_init",
                )
                return json.dumps({"error": error_msg, "results": []})

        def run_query(sql: str):
            return test_db.execute_sql(sql)

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_query, sql)  # Pass 'sql' as an argument
            try:
                # Wait for the query to complete within the specified timeout
                result = future.result(timeout=timeout)
                return json.dumps(result)
            except TimeoutError:
                logger.warning(
                    "SQL query execution timeout",
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    timeout=timeout,
                    operation="sql_query_timeout",
                )
                return json.dumps({"error": "Query timed out", "results": []})
            except Exception as e:
                logger.error(
                    "SQL query execution error",
                    error=str(e),
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    operation="sql_query_error",
                )
                return json.dumps({"error": str(e), "results": []})

    @staticmethod
    def execute_sql_azure(
        sql: str,
        timeout: int = 15,  # Timeout in seconds
    ) -> str:
        def run_query(sql_query):
            try:
                # Use global cursor if available, otherwise create new connection
                if cursor is not None:
                    cursor.execute(sql_query)
                    r = [
                        dict(
                            (cursor.description[i][0], value)
                            for i, value in enumerate(row)
                        )
                        for row in cursor.fetchall()
                    ]
                else:
                    # Create temporary connection
                    conn_temp, cursor_temp = get_conn(_config)
                    cursor_temp.execute(sql_query)
                    r = [
                        dict(
                            (cursor_temp.description[i][0], value)
                            for i, value in enumerate(row)
                        )
                        for row in cursor_temp.fetchall()
                    ]
                    conn_temp.close()
                return json.dumps(r)
            except Exception as query_err:
                logger.error(
                    "Azure SQL query execution failed",
                    error=str(query_err),
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    operation="azure_sql_query_error",
                )
                return json.dumps({"error": f"Query Error: {query_err}", "results": []})

        # Run query in a separate thread with a timeout
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_query, sql)
            try:
                result = future.result(timeout=timeout)
                return result
            except TimeoutError:
                logger.warning(
                    "Azure SQL query timeout",
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    timeout=timeout,
                    operation="azure_sql_query_timeout",
                )
                return json.dumps({"error": "Query timed out", "results": []})
            except Exception as e:
                logger.error(
                    "Azure SQL execution error",
                    error=str(e),
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    operation="azure_sql_execution_error",
                )
                return json.dumps({"error": f"Execution Error: {e}", "results": []})
