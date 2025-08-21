from flask import Blueprint, jsonify, send_file, request
import os
import logging

api_blueprint = Blueprint('api', __name__, url_prefix='/api')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_api_blueprint(db_manager, processor, chart_generator):

    @api_blueprint.route('/profile_results', methods=['GET'])
    def get_profile_results():
        try:
            all_results = db_manager.get_all_profile_results()
            
            if not all_results:
                return jsonify({'message': 'No profile results found.'}), 404

            grouped_data = {}
            for row in all_results:
                device_id = row['device_id']
                test_group = row['test_group_id']
                test_method = row['test_method']

                device_dict = grouped_data.setdefault(device_id, {})
                test_group_dict = device_dict.setdefault(test_group, {})
                
                # 將儲存的字串轉換回數字陣列
                txs_str = row.get('captured_txs', '')
                rxs_str = row.get('captured_rxs', '')
                
                captured_txs = [int(val) for val in txs_str.split(',') if val] if txs_str else []
                captured_rxs = [int(val) for val in rxs_str.split(',') if val] if rxs_str else []
                
                test_group_dict[test_method] = {
                    'avg_tx': row['avg_tx'],
                    'avg_rx': row['avg_rx'],
                    'timestamp': row['timestamp'],
                    'captured_txs': captured_txs, # 回傳陣列
                    'captured_rxs': captured_rxs  # 回傳陣列
                }
            
            return jsonify(grouped_data)

        except Exception as e:
            logger.error(f"Error in /profile_results endpoint: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred.'}), 500

    
     # --- 刪除特定profile測試組的 API ---
    @api_blueprint.route('/profile_results/<string:device_id>/<string:test_group_id>', methods=['DELETE'])
    def delete_profile_group(device_id, test_group_id):
        try:
            if db_manager.delete_profile_results_by_group(device_id, test_group_id):
                return jsonify({'message': f"Successfully deleted profile results for device {device_id}, group {test_group_id}."}), 200
            else:
                return jsonify({'message': f"No profile results found for device {device_id}, group {test_group_id} to delete."}), 200
        except Exception as e:
            logger.error(f"Error deleting profile group for device {device_id}: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred.'}), 500

    # --- 刪除特定profile節點所有資料的 API ---
    @api_blueprint.route('/profile_results/<string:device_id>', methods=['DELETE'])
    def delete_all_profiles_for_device(device_id):
        try:
            if db_manager.delete_all_profile_results_for_device(device_id):
                return jsonify({'message': f"Successfully deleted all profile results for device {device_id}."}), 200
            else:
                return jsonify({'message': f"No profile results found for device {device_id} to delete."}), 200
        except Exception as e:
            logger.error(f"Error deleting all profiles for device {device_id}: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred.'}), 500

    
    @api_blueprint.route('/chart-data')
    def get_chart_data_api():
        try:
            df = db_manager.get_average_rates_as_dataframe()
            
            if df.empty:
                return jsonify({'error': 'No data available to generate chart data.'}), 404
            
            chart_data = chart_generator.get_chart_data(df)
            
            return jsonify(chart_data)
            
        except Exception as e:
            # 增加錯誤處理
            logger.error(f"Error in /chart-data endpoint: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred.'}), 500
    @api_blueprint.route('/chart')
    def get_chart():
        chart_path = "chart.png"
        if not os.path.exists(chart_path):

            csv_path = db_manager.export_to_csv()
            if csv_path:
                chart_generator.generate_chart(csv_path)
            else:
                return jsonify({'error': 'CSV data not available to generate chart.'}), 404

        if not os.path.exists(chart_path):
            return jsonify({'error': 'Chart file not yet generated.'}), 404
            
        return send_file(chart_path, mimetype='image/png')

    @api_blueprint.route('/data')
    def get_data():
        csv_path = db_manager.export_to_csv()
        if not csv_path:
            return jsonify({'error': 'Failed to export CSV.'}), 500
        return send_file(csv_path, mimetype='text/csv')
    
    @api_blueprint.route('/get_all_data', methods=['GET'])
    def get_all_data():
        # Retrieve data from the database
        data = db_manager.get_all_data()
        if not data:
            return jsonify({'error': 'No data found.'}), 404
        return jsonify(data)

    @api_blueprint.route('/get_all_average_rates_data', methods=['GET'])
    def get_all_average_rates_data():
        # Retrieve data from the database
        data = db_manager.get_all_average_rates_data()
        if not data:
            return jsonify({'error': 'No data found.'}), 404
        return jsonify(data)
    
    @api_blueprint.route('/get_all_raw_log', methods=['GET'])
    def get_all_raw_log():
        # Retrieve data from the database
        data = db_manager.get_all_raw_log()
        if not data:
            return jsonify({'error': 'No raw log data found.'}), 404
        return jsonify(data)

    @api_blueprint.route('/clear_database', methods=['POST'])
    def clear_database():
        data = request.json
        if not data or data.get('confirm') != 'yes':
            return jsonify({'error': 'Dangerous operation. Please include {"confirm": "yes"} in the JSON body to confirm.'}), 400
        
        if db_manager.clear_all_data():
            return jsonify({'message': 'Database cleared successfully.'}), 200
        else:
            return jsonify({'error': 'Internal error while clearing the database.'}), 500

    @api_blueprint.route('/test_groups', methods=['GET'])
    def get_test_groups():
        groups = db_manager.get_all_test_groups()
        return jsonify(groups)

    @api_blueprint.route('/delete_test', methods=['POST'])
    def delete_test_group():
        data = request.json
        display_name = data.get('display_name') if data else None

        if not display_name:
            return jsonify({'error': 'Missing "display_name" in request body.'}), 400
        
        existing_groups = db_manager.get_all_test_groups()
        if display_name not in existing_groups:
             return jsonify({'error': f"Test group '{display_name}' not found."}), 404

        if db_manager.delete_test_group_data(display_name):
            # csv_path = db_manager.export_to_csv()
            # if csv_path:
            #     chart_generator.generate_chart(csv_path)
            return jsonify({'message': f"Successfully deleted all data for test group '{display_name}'."}), 200
        else:
            return jsonify({'error': f"An internal error occurred while deleting test group '{display_name}'."}), 500

    return api_blueprint