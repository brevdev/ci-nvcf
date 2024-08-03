# common.py
import os
import base64
import requests
import yaml
from requests.exceptions import HTTPError, ConnectionError
from types import SimpleNamespace
import traceback

class BaseClass:
    # Mapping of scopes to their corresponding API URLs
    SCOPE_API_MAP = {
        "update_function": "https://api.ngc.nvidia.com/v2/nvcf" ,
        "register_function": "https://api.ngc.nvidia.com/v2/nvcf",
        "queue_details": "https://api.nvcf.nvidia.com/v2/nvcf",
        "list_functions": "https://api.ngc.nvidia.com/v2/nvcf",
        "list_cluster_groups": "https://api.ngc.nvidia.com/v2/nvcf",
        "invoke_function": "https://api.nvcf.nvidia.com/v2/nvcf",
        "deploy_function": "https://api.ngc.nvidia.com/v2/nvcf",
        "delete_function": "https://api.ngc.nvidia.com/v2/nvcf"
    }

    def load_environment_variables(self):
        # Determine the prefix based on the environment
        prefix = "PRD_" if self.environment == "production" else ""

        # Load environment variables with the determined prefix
        self.nvcf_api_key = os.getenv(f"{prefix}NVCF_API_KEY")

    def _convert_dict_to_object(self, dictionary):
        if isinstance(dictionary, dict):
            for key, value in dictionary.items():
                dictionary[key] = self._convert_dict_to_object(value)
            return SimpleNamespace(**dictionary)
        elif isinstance(dictionary, list):
            return [self._convert_dict_to_object(item) for item in dictionary]
        else:
            return dictionary

    def _list_nvcf_fn(self, logger):
        url = self.SCOPE_API_MAP["list_functions"]
        # Check for functions and match by name
        logger.info(f"{self.job_name}: Listing NVCF functions.")

        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.nvcf_api_key}"}
            response = requests.get(f"{url}/functions", headers=headers)
            response.raise_for_status()
            data = response.json()

            if data is None or "functions" not in data:
                logger.error("No functions data received from API")

            functions_list = data.get("functions", [])
            self.functions_objects = [SimpleNamespace(**function) for function in functions_list]

        except requests.HTTPError as http_err:
            logger.error(f"{self.job_name}: HTTP error occurred: {http_err}")
            logger.error(f"Response Body: {response.text}")
            # Log the traceback for more detail
            logger.error(traceback.format_exc())
            # Handle specific HTTP errors or re-raise
            raise
        except requests.RequestException as req_err:
            logger.error(f"{self.job_name}: Request error occurred: {req_err}")
            # Log the traceback for more detail
            logger.error(traceback.format_exc())
            # Handle other request-related errors or re-raise
            raise

    def _digest_manifest(self, manifest_path, logger):
        logger.info(f"{self.job_name}: Parsing Manifest at {manifest_path}")

        with open(manifest_path, "r") as file:
            manifest_data = yaml.safe_load(file)
            if manifest_data is None:
                logger.error(f"Manifest data is None. Check the YAML file at {manifest_path}")
                sys.exit(1)  # or handle it appropriately
        # Convert the dictionary to SimpleNamespace recursively
        def convert_to_simple_namespace(d):
            if isinstance(d, dict):
                return SimpleNamespace(**{k: convert_to_simple_namespace(v) for k, v in d.items()})
            elif isinstance(d, list):
                return [convert_to_simple_namespace(item) for item in d]
            else:
                return d

        self.manifest = convert_to_simple_namespace(manifest_data)
