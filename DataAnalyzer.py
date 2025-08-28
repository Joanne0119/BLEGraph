import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class DataAnalyzer:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def _prepare_data(self):
        profile_data_list = self.db_manager.get_all_profile_results()
        if not profile_data_list:
            return pd.DataFrame()
        records = []
        for row in profile_data_list:
            record = {"device_id": row['device_id'], "test_method": row['test_method']}
            txs_str = row.get('captured_txs', '')
            tx_values = [int(v) for v in txs_str.split(',') if v] if txs_str else []
            if tx_values:
                record['tx_median'] = np.median(tx_values)
                q75, q25 = np.percentile(tx_values, [75, 25])
                record['tx_stability_iqr'] = q75 - q25
            rxs_str = row.get('captured_rxs', '')
            rx_values = [int(v) for v in rxs_str.split(',') if v] if rxs_str else []
            if rx_values:
                record['rx_median'] = np.median(rx_values)
                q75, q25 = np.percentile(rx_values, [75, 25])
                record['rx_stability_iqr'] = q75 - q25
            records.append(record)
        return pd.DataFrame(records).dropna(subset=['tx_median', 'rx_median'])


    def rank_nodes_by_performance(self, strength_weight=0.5, stability_weight=0.5):
        """
        使用百分比排名 (Percentile Rank) 進行評分
        """
        try:
            logger.info("Starting node ranking with PERCENTILE RANK model...")
            df = self._prepare_data()
            if df.empty:
                return []

            df['tx_strength_score'] = df.groupby('test_method')['tx_median'].transform(lambda x: x.rank(pct=True) * 100)
            df['rx_strength_score'] = df.groupby('test_method')['rx_median'].transform(lambda x: x.rank(pct=True) * 100)
     
            df['tx_stability_score'] = df.groupby('test_method')['tx_stability_iqr'].transform(lambda x: x.rank(ascending=True, pct=True) * 100)
            df['rx_stability_score'] = df.groupby('test_method')['rx_stability_iqr'].transform(lambda x: x.rank(ascending=True, pct=True) * 100)
            
            df.fillna(50, inplace=True)

            df['tx_score'] = (df['tx_strength_score'] * strength_weight) + (df['tx_stability_score'] * stability_weight)
            df['rx_score'] = (df['rx_strength_score'] * strength_weight) + (df['rx_stability_score'] * stability_weight)
            df['comprehensive_score_per_test'] = (df['tx_score'] + df['rx_score']) / 2

            final_ranking = df.groupby('device_id').agg(
                tx_performance_score=('tx_score', 'mean'),
                rx_performance_score=('rx_score', 'mean'),
                comprehensive_score=('comprehensive_score_per_test', 'mean')
            ).reset_index()

            final_ranking.sort_values(by='comprehensive_score', ascending=False, inplace=True)
            
            final_ranking['rank'] = range(1, len(final_ranking) + 1)
            
            logger.info(f"Percentile ranking complete for {len(final_ranking)} devices.")
            
            agg_metrics = df.groupby('device_id').agg(
                avg_tx_strength=('tx_median', 'mean'),
                avg_tx_stability=('tx_stability_iqr', 'mean'),
                avg_rx_strength=('rx_median', 'mean'),
                avg_rx_stability=('rx_stability_iqr', 'mean')
            ).reset_index()
            
            final_df = pd.merge(final_ranking, agg_metrics, on='device_id')
            
            return final_df.to_dict(orient='records')

        except Exception as e:
            logger.error(f"Error during percentile ranking: {e}", exc_info=True)
            return []