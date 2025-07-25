from flask import Blueprint, jsonify, send_file, request
import os
import logging

api_blueprint = Blueprint('api', __name__, url_prefix='/api')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_api_blueprint(db_manager, processor, chart_generator):
    
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
            csv_path = db_manager.export_to_csv()
            if csv_path:
                chart_generator.generate_chart(csv_path)
            return jsonify({'message': f"Successfully deleted all data for test group '{display_name}'."}), 200
        else:
            return jsonify({'error': f"An internal error occurred while deleting test group '{display_name}'."}), 500

    return api_blueprint