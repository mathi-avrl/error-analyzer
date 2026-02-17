import logging
import uuid
import orjson
from google.cloud import datastore
from datetime import datetime, timedelta

# Initialize the Datastore client
datastore_client = datastore.Client()

# Set up logging
logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d:%H:%M:%S', level=logging.INFO)
logger = logging.getLogger(__name__)
 
def update_datastore(client_name, account_name, avrl_user_id, error_message, request_body):
    try:
       
        # Step 1: Generate a unique ID for the new entity using UUID
        unique_id = str(uuid.uuid4())  # Generate a random unique ID
        logger.debug(f"Generated new unique ID: {unique_id}")

        # Step 2: Create a key for the new entity with the kind 'phoenix_test'
        entity_key = datastore_client.key('phoenix_test', unique_id)  # 'phoenix_test' is the kind, unique_id is the entity ID
        logger.debug(f"Entity key created: {entity_key}")

        # Step 3: Create the entity and add data
        entity = datastore.Entity(key=entity_key)
        created_at = datetime.now()
        expire_at = created_at + timedelta(days=30)
        entity.update({
            'client_name': client_name,
            'account_name': account_name,
            'avrl_user_id': avrl_user_id,
            'error_message': error_message,
            'request_body': request_body,
            'created_at': created_at,
            'expire_at': expire_at
        })
        logger.debug(f"Created entity object: {entity}")

        # Step 4: Save the entity to Datastore
        datastore_client.put(entity)
        logger.info(f"Datastore entity created with ID: {unique_id} for client: {client_name}")

        return {'status': 'success', 'message': 'Entity created successfully in Datastore'}

    except Exception as e:
        logger.error(f"Error creating Datastore entity: {e}")
        return {'status': 'failed', 'message': f"Error creating Datastore entity: {e}"}


def get_bot_metrics(selected_date, client_name):

    """
    Fetch phoenix_test entities filtered by created_at date and parse bot data from error messages.
    Extracts unique tree names and accumulates counts for display.
    Categorizes errors as authentication failures or malformed requests based on content.
    
    :param selected_date: Date string in format 'YYYY-MM-DD'. If None, uses current date.
    """
    try:
        from datetime import datetime, date
        
        # Use current date if no date provided
        if selected_date is None:
            selected_date = date.today().isoformat()
        
        # Parse the selected date
        try:
            selected_date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            logger.error(f"Invalid date format: {selected_date}")
            return []


        client_name_str = client_name.strip().lower()

        logger.info(f"Fetching bot metrics for client_name={client_name_str}, date={selected_date_obj}")

        query = datastore_client.query(kind="phoenix_test")
        query.add_filter(filter=("client_name", "=", client_name_str))
        entities = list(query.fetch())
                
        # Dictionary to store unique tree names and their data
        tree_data = {}
        
        for entity in entities:
            # Filter by created_at date
            created_at = entity.get('created_at')
            if created_at:
                # Convert to date object for comparison
                if hasattr(created_at, 'date'):
                    entity_date = created_at.date()
                else:
                    entity_date = created_at
                
                # Skip if date doesn't match
                if entity_date != selected_date_obj:
                    continue
            
            error_message_entity = entity.get('error_message')
            
            if not error_message_entity:
                continue
            
            # Parse error_message if it's a JSON string
            if isinstance(error_message_entity, str):
                try:
                    error_message_entity = orjson.loads(error_message_entity)
                except (orjson.JSONDecodeError, ValueError):
                    logger.warning(f"Failed to parse error_message as JSON: {error_message_entity}")
                    continue
            
            # Extract caller_details to get tree name
            caller_details = error_message_entity.get('caller_details', '')
            parts = caller_details.split(':')
            
            # Tree name is the second part (index 1)
            tree_name = parts[1] if len(parts) > 1 else 'unknown'
            
            # Skip if tree name is "treename-not-set" or empty
            if tree_name == '' or tree_name == 'unknown':
                continue
            
            # Initialize tree_data entry if not exists
            if tree_name not in tree_data:
                tree_data[tree_name] = {
                    'bot_name': tree_name,
                    'error_code': '',
                    'error_message': '',
                    'current_time': '',
                    'errors_list': [],  # Store all errors
                    'request_body': {},
                    'phoenix_requests': {'pre_8am': 0, '8am_6pm': 0, 'post_6pm': 0},
                    'auth_failures': {'pre_8am': 0, '8am_6pm': 0, 'post_6pm': 0},
                    'malformed_requests': {'pre_8am': 0, '8am_6pm': 0, 'post_6pm': 0},
                    'api_failures': {'pre_8am': 0, '8am_6pm': 0, 'post_6pm': 0}
                }
            
            # Get error details
            error_code = error_message_entity.get('error_code', '')
            error_msg = error_message_entity.get('error_message', '')
            current_time = error_message_entity.get('current_time', '')
            
            # Store request_body if available
            request_body = entity.get('request_body', {})
            if request_body and not tree_data[tree_name]['request_body']:
                tree_data[tree_name]['request_body'] = request_body
            
            # Store the latest error details (for backward compatibility)
            tree_data[tree_name]['error_code'] = error_code
            tree_data[tree_name]['error_message'] = error_msg
            tree_data[tree_name]['current_time'] = current_time
            
            # Get error message text
            # error_msg_text = error_msg.lower()
            error_msg_text = error_msg
            is_auth_failure = 'authenticate' in error_msg_text
            
            # Check if error code is in API failure range (600-700)
            is_api_failure = False
            try:
                error_code_num = int(error_code) if error_code else 0
                is_api_failure = 600 <= error_code_num <= 700
            except (ValueError, TypeError):
                pass
            
            # Extract time period from current_time
            time_period = extract_time_period(current_time)

            # determine error type
            if is_api_failure:
                error_type = 'api'
            elif is_auth_failure:
                error_type = 'auth'
            else:
                error_type = 'malformed'

            tree_data[tree_name]['errors_list'].append({
                'error_code': error_code,
                'error_message': error_msg,
                'current_time': current_time,
                'time_period': time_period,
                'error_type': error_type,
                'request_body': request_body
            })
            if time_period:
                # Update phoenix_requests total (increment count)
                tree_data[tree_name]['phoenix_requests'][time_period] += 1
                
                # Update specific category based on error type (increment count)
                if is_api_failure:
                    tree_data[tree_name]['api_failures'][time_period] += 1
                elif is_auth_failure:
                    tree_data[tree_name]['auth_failures'][time_period] += 1
                else:
                    tree_data[tree_name]['malformed_requests'][time_period] += 1
        
        # Convert to list for JSON serialization and format counts
        bot_data = []
        for tree_name, data in tree_data.items():
            bot_data.append({
                'bot_name': tree_name,
                'error_code': data['error_code'],
                'error_message': data['error_message'],
                'current_time': data['current_time'],
                'errors_list': data['errors_list'],
                'request_body': data['request_body'],
                'phoenix_requests': {
                    'pre_8am': format_count(data['phoenix_requests']['pre_8am']),
                    '8am_6pm': format_count(data['phoenix_requests']['8am_6pm']),
                    'post_6pm': format_count(data['phoenix_requests']['post_6pm'])
                },
                'auth_failures': {
                    'pre_8am': format_count(data['auth_failures']['pre_8am']),
                    '8am_6pm': format_count(data['auth_failures']['8am_6pm']),
                    'post_6pm': format_count(data['auth_failures']['post_6pm'])
                },
                'malformed_requests': {
                    'pre_8am': format_count(data['malformed_requests']['pre_8am']),
                    '8am_6pm': format_count(data['malformed_requests']['8am_6pm']),
                    'post_6pm': format_count(data['malformed_requests']['post_6pm'])
                },
                'api_failures': {
                    'pre_8am': format_count(data['api_failures']['pre_8am']),
                    '8am_6pm': format_count(data['api_failures']['8am_6pm']),
                    'post_6pm': format_count(data['api_failures']['post_6pm'])
                }
            })
        
        logger.info(f"Fetched {len(bot_data)} unique bot metrics from {len(entities)} total entities for date {selected_date}")
        return bot_data
        
    except Exception as e:
        logger.error(f"Error fetching bot metrics: {e}")
        return []

def extract_time_period(time_str):
    """
    Extract time period from current_time string.
    Format: '2025-12-10:23:40:43 GMT +0530'
    Returns: 'pre_8am', '8am_6pm', or 'post_6pm'
    """
    try:
        if not time_str:
            return None
        
        # Extract the time part (HH:MM:SS) from the string
        # Split by space to get the date:time part
        datetime_part = time_str.split(' ')[0]  # '2025-12-10:23:40:43'
        
        # Split by colon and get the hour (second element after date)
        parts = datetime_part.split(':')
        if len(parts) < 2:
            return None
        
        # parts[0] = date, parts[1] = hour, parts[2] = minute, parts[3] = second
        hour = int(parts[1])
        
        # Categorize based on hour
        if hour < 8:
            return 'pre_8am'
        elif hour < 18:
            return '8am_6pm'
        else:
            return 'post_6pm'
    except Exception as e:
        logger.debug(f"Error extracting time period from {time_str}: {e}")
        return None

def format_count(count):
    """Convert count to string or dash if zero."""
    return str(count) if count > 0 else '-'