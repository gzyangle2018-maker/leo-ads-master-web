"""
Leo Ads Master - Report Parser Module
自动识别亚马逊广告报表类型，映射列名，清洗数据
"""
import re
from typing import Dict, List, Tuple, Optional
import pandas as pd


class ReportParser:
    """报表解析器：自动识别报表类型，映射标准列名"""

    # 标准列名映射表（目标字段 -> 可能的来源列名）
    COLUMN_ALIASES = {
        # Campaign / Ad Group / Keyword
        'campaign': ['Campaign', 'Campaign Name', '广告活动', '广告活动名称', 'CampaignName', 'campaign_name',
                     '广告活动名称(Campaign)', 'Campaign name', '广告活动名称（Campaign）'],
        'ad_group': ['Ad Group', 'AdGroup', '广告组', '广告组名称', 'AdGroup Name', 'ad_group_name',
                     '广告组名称(Ad Group)', 'Ad group', '广告组名称（Ad Group）'],
        'keyword': ['Keyword', 'Search Term', 'Customer Search Term', '搜索词', '关键词',
                    'keyword_text', 'search_term', 'customer_search_term', '客户搜索词'],
        'match_type': ['Match Type', '匹配类型', 'match_type', '匹配方式'],
        'ad_type': ['Campaign Type', '广告类型', 'Placement', 'ad_type', '类型'],
        'budget': ['Budget', 'Daily Budget', '预算', 'budget', '每日预算'],
        'bid': ['Bid', 'Max Bid', 'Default Bid', '出价', '竞价', 'bid', '竞价(USD)', '默认竞价'],
        # 指标字段
        'impressions': ['Impressions', '曝光', '展示次数', 'impressions', '展示量', 'Impr.'],
        'clicks': ['Clicks', '点击', '点击次数', 'clicks', '点击量'],
        'spend': ['Spend', 'Cost', '花费', '广告费', 'spend', 'cost', 'Spend (USD)', '广告花费'],
        'sales': ['Sales', 'Ordered Product Sales', '销售额', 'sales', 'Sales (USD)', '广告销售额'],
        'orders': ['Orders', 'Total Orders', '订单数', '订单', 'orders', 'Total Order', '广告订单'],
        'acos': ['ACOS', 'ACoS', '广告销售成本比', 'acos', 'Total Advertising Cost of Sales (ACoS)',
                 'Advertising Cost of Sales (ACoS)', 'Total ACoS ', 'ACoS ', '总广告销售成本比(ACoS)'],
        'roas': ['ROAS', '广告支出回报率', 'roas', 'Return on Ad Spend (ROAS)'],
        'ctr': ['CTR', 'Click-Thru Rate', '点击率', 'ctr', 'Click-Thru Rate (CTR)'],
        'cvr': ['CVR', 'Conversion Rate', '转化率', 'cvr', 'Conversion Rate (CVR)', '订单转化率'],
        'cpc': ['CPC', 'Cost Per Click', '平均点击成本', 'cpc', 'Cost Per Click (CPC)'],
        # Search Term Report 特有
        'search_term': ['Search Term', 'Customer Search Term', '搜索词', 'search_term', '客户搜索词'],
        # Placement Report 特有
        'placement': ['Placement', '广告位', 'placement', '广告位(Placement)'],
        # Business Report 特有
        'sessions': ['Sessions', '买家访问次数', 'Sessions - Total', 'sessions', '访问次数'],
        'page_views': ['Page Views', '页面浏览次数', 'page_views', '浏览次数'],
        'units_ordered': ['Units Ordered', '订单商品数量', 'units_ordered', 'Units Ordered - Total', '订购数量'],
        'ordered_product_sales': ['Ordered Product Sales', '已订购商品销售额', 'ordered_product_sales', 'Product Sales',
                                   '销售额', 'Ordered Product Sales - Total'],
        'buy_box': ['Buy Box Percentage', '购买按钮赢得率', 'buy_box', 'Buy Box %'],
        'parent_asin': ['Parent ASIN', '父商品', '父ASIN', '父商品ASIN', 'Parent'],
        'child_asin': ['Child ASIN', '子商品', '子ASIN', '子商品ASIN', 'ASIN', 'asin'],
        'sku': ['SKU', 'sku'],
        'units_per_session': ['Unit Session Percentage', 'Session Percentage', ' units per session',
                               'units_per_session', '订单转化率'],
    }

    # 报表类型识别规则
    REPORT_TYPE_PATTERNS = {
        'sp_search_term': {
            'required_cols': ['search_term', 'campaign', 'ad_group'],
            'keywords': ['search term', 'customer search', 'search_term', '搜索词', '客户搜索词'],
            'score': 0
        },
        'sp_targeting': {
            'required_cols': ['keyword', 'campaign', 'ad_group', 'match_type'],
            'keywords': ['targeting', 'keyword', 'match type', '匹配方式', '匹配类型'],
            'score': 0
        },
        'sp_campaign': {
            'required_cols': ['campaign', 'budget', 'spend', 'sales', 'acos'],
            'keywords': ['campaign', 'budget', 'spend', 'sales', '广告活动', '预算', '花费'],
            'score': 0
        },
        'sp_adgroup': {
            'required_cols': ['campaign', 'ad_group', 'spend', 'sales'],
            'keywords': ['ad group', 'ad_group', '广告组'],
            'score': 0
        },
        'sp_placement': {
            'required_cols': ['campaign', 'placement', 'spend', 'sales'],
            'keywords': ['placement', '广告位', 'top of search'],
            'score': 0
        },
        'sb_campaign': {
            'required_cols': ['campaign', 'spend', 'sales'],
            'keywords': ['sponsored brands', 'sb ', '品牌', '品牌推广'],
            'score': 0
        },
        'sb_search_term': {
            'required_cols': ['search_term', 'campaign'],
            'keywords': ['sponsored brands', 'search term', '品牌搜索词'],
            'score': 0
        },
        'sd_campaign': {
            'required_cols': ['campaign', 'spend', 'sales'],
            'keywords': ['sponsored display', 'sd ', '展示型', '展示型推广'],
            'score': 0
        },
        'business_report': {
            'required_cols': [],
            'keywords': ['sessions', 'units ordered', 'ordered product sales', 'business',
                         '买家访问', '订单商品', '已订购商品', '业务报告', '浏览次数'],
            'score': 0
        },
    }

    def __init__(self):
        pass

    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名：将各种变体映射到标准字段"""
        col_map = {}
        for standard, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                for col in df.columns:
                    if col.strip().lower() == alias.strip().lower():
                        col_map[col] = standard
                        break
        return df.rename(columns=col_map)

    def detect_report_type(self, df: pd.DataFrame) -> Tuple[str, float]:
        """自动识别报表类型，返回 (类型, 置信度)"""
        if df.empty:
            return 'unknown', 0.0

        cols_lower = [c.strip().lower() for c in df.columns]
        scores = {}

        for report_type, rules in self.REPORT_TYPE_PATTERNS.items():
            score = 0
            # 检查关键词匹配
            for kw in rules['keywords']:
                for col in cols_lower:
                    if kw in col:
                        score += 2

            # 检查必需列
            required_found = 0
            for req in rules['required_cols']:
                req_aliases = self.COLUMN_ALIASES.get(req, [req])
                for alias in req_aliases:
                    if any(alias.strip().lower() == c for c in cols_lower):
                        required_found += 1
                        score += 3
                        break

            scores[report_type] = score

        if not scores:
            return 'unknown', 0.0

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # 归一化置信度（最高约 20 分）
        confidence = min(best_score / 20.0, 1.0)
        return best_type, confidence

    def parse_file(self, file_bytes: bytes, filename: str) -> Dict:
        """解析单个文件，返回标准化后的数据"""
        try:
            if filename.lower().endswith('.csv'):
                # Try multiple encodings
                for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
                    try:
                        df = pd.read_csv(pd.io.common.BytesIO(file_bytes), encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    df = pd.read_csv(pd.io.common.BytesIO(file_bytes), encoding='utf-8', errors='replace')
            else:
                df = pd.read_excel(pd.io.common.BytesIO(file_bytes))
        except Exception as e:
            return {'success': False, 'error': f'文件解析失败: {str(e)}'}

        if df.empty:
            return {'success': False, 'error': '文件为空'}

        raw_rows = len(df)

        # 检测报表类型
        report_type, confidence = self.detect_report_type(df)

        # 标准化列名
        df_norm = self.normalize_columns(df)

        # 清洗数据
        df_clean = self._clean_data(df_norm, report_type)

        # 过滤掉全空行
        df_clean = df_clean.dropna(how='all')

        # 将 Timestamp 等非 JSON 序列化类型转为字符串
        for col in df_clean.columns:
            if df_clean[col].dtype.name.startswith('datetime'):
                df_clean[col] = df_clean[col].astype(str)
            elif df_clean[col].dtype == 'object':
                # 确保所有 object 列都是字符串
                df_clean[col] = df_clean[col].astype(str).replace('nan', '').replace('None', '')

        return {
            'success': True,
            'filename': filename,
            'report_type': report_type,
            'confidence': confidence,
            'columns': list(df.columns),
            'normalized_columns': list(df_norm.columns),
            'raw_rows': raw_rows,
            'rows': len(df_clean),
            'preview': df_clean.head(5).to_dict(orient='records'),
            'data': df_clean.to_dict(orient='records')
        }

    def _clean_data(self, df: pd.DataFrame, report_type: str) -> pd.DataFrame:
        """数据清洗"""
        # 复制一份避免修改原数据
        df = df.copy()

        numeric_cols = ['impressions', 'clicks', 'spend', 'sales', 'orders', 'acos', 'roas', 'ctr', 'cvr', 'cpc', 'bid', 'budget',
                        'units_ordered', 'ordered_product_sales', 'sessions', 'page_views', 'buy_box', 'units_per_session']
        for col in numeric_cols:
            if col in df.columns:
                # 先转成字符串，然后去掉 $ % , 空格，再转数字
                cleaned = df[col].astype(str).str.replace(r'[\$%,\s]', '', regex=True)
                # 处理空字符串和 '-' '—'
                cleaned = cleaned.replace(['', '-', '—', 'N/A', 'n/a', 'NA'], '0')
                df[col] = pd.to_numeric(cleaned, errors='coerce').fillna(0)

        # 字符串字段去空格
        str_cols = ['campaign', 'ad_group', 'keyword', 'search_term', 'match_type', 'placement', 'asin', 'sku', 'parent_asin', 'child_asin']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().fillna('')
                # 把 'nan' 字符串替换为空
                df[col] = df[col].replace('nan', '')

        return df

    def extract_campaign_data(self, parsed_reports: List[Dict]) -> List[Dict]:
        """从解析后的报表中提取 campaign 级别数据用于分析"""
        campaigns = []

        for report in parsed_reports:
            if not report.get('success'):
                continue

            data = report.get('data', [])
            report_type = report.get('report_type', 'unknown')

            if not data:
                continue

            for row in data:
                camp_name = row.get('campaign', '')
                if not camp_name:
                    continue

                # 提取 ASIN
                asin = self._extract_asin(row, camp_name)

                # 根据报表类型提取不同粒度的数据
                if 'search_term' in report_type:
                    keyword = row.get('search_term', row.get('keyword', ''))
                    if not keyword:
                        continue
                    campaigns.append({
                        'asin': asin,
                        'campaign': camp_name,
                        'ad_group': row.get('ad_group', ''),
                        'ad_type': self._infer_ad_type(camp_name, report_type),
                        'budget': float(row.get('budget', 0) or 0),
                        'acos_3d': float(row.get('acos', 0) or 0) * 0.9,
                        'acos_30d': float(row.get('acos', 0) or 0),
                        'bid': float(row.get('bid', 0) or 0),
                        'clicks': int(row.get('clicks', 0) or 0),
                        'orders': int(row.get('orders', 0) or 0),
                        'keyword': keyword,
                        'cvr': float(row.get('cvr', 0) or 0),
                        'is_core': False,
                        'search_volume': str(row.get('search_volume', '缺失')),
                        'aba_rank': str(row.get('aba_rank', '缺失')),
                        'spend': float(row.get('spend', 0) or 0),
                        'sales': float(row.get('sales', 0) or 0),
                    })
                elif 'campaign' in report_type or 'adgroup' in report_type:
                    campaigns.append({
                        'asin': asin,
                        'campaign': camp_name,
                        'ad_group': row.get('ad_group', ''),
                        'ad_type': self._infer_ad_type(camp_name, report_type),
                        'budget': float(row.get('budget', 0) or 0),
                        'acos_3d': float(row.get('acos', 0) or 0) * 0.9,
                        'acos_30d': float(row.get('acos', 0) or 0),
                        'bid': float(row.get('bid', 0) or 0),
                        'clicks': int(row.get('clicks', 0) or 0),
                        'orders': int(row.get('orders', 0) or 0),
                        'keyword': row.get('keyword', row.get('search_term', '')),
                        'cvr': float(row.get('cvr', 0) or 0),
                        'is_core': False,
                        'search_volume': '缺失',
                        'aba_rank': '缺失',
                        'spend': float(row.get('spend', 0) or 0),
                        'sales': float(row.get('sales', 0) or 0),
                    })
                elif 'targeting' in report_type:
                    campaigns.append({
                        'asin': asin,
                        'campaign': camp_name,
                        'ad_group': row.get('ad_group', ''),
                        'ad_type': self._infer_ad_type(camp_name, report_type),
                        'budget': float(row.get('budget', 0) or 0),
                        'acos_3d': float(row.get('acos', 0) or 0) * 0.9,
                        'acos_30d': float(row.get('acos', 0) or 0),
                        'bid': float(row.get('bid', 0) or 0),
                        'clicks': int(row.get('clicks', 0) or 0),
                        'orders': int(row.get('orders', 0) or 0),
                        'keyword': row.get('keyword', row.get('search_term', '')),
                        'cvr': float(row.get('cvr', 0) or 0),
                        'is_core': False,
                        'search_volume': '缺失',
                        'aba_rank': '缺失',
                        'spend': float(row.get('spend', 0) or 0),
                        'sales': float(row.get('sales', 0) or 0),
                    })
                elif 'business' in report_type:
                    # 业务报告提取 ASIN 和销售数据
                    campaigns.append({
                        'asin': asin,
                        'campaign': f"Organic_{asin}",
                        'ad_group': 'Organic',
                        'ad_type': 'Organic',
                        'budget': 0,
                        'acos_3d': 0,
                        'acos_30d': 0,
                        'bid': 0,
                        'clicks': int(row.get('sessions', 0) or 0),
                        'orders': int(row.get('units_ordered', 0) or 0),
                        'keyword': 'Organic Traffic',
                        'cvr': float(row.get('units_per_session', 0) or 0),
                        'is_core': True,
                        'search_volume': '缺失',
                        'aba_rank': '缺失',
                        'spend': 0,
                        'sales': float(row.get('ordered_product_sales', 0) or 0),
                    })

        return campaigns

    def _extract_asin(self, row: dict, campaign_name: str) -> str:
        """从行数据或 Campaign 名称中提取 ASIN"""
        # 1. 优先从行的 asin / child_asin / parent_asin 字段提取
        for key in ['asin', 'child_asin', 'parent_asin']:
            val = str(row.get(key, '')).strip().upper()
            if val and val != 'NAN' and re.match(r'^[A-Z0-9]{10}$', val):
                return val

        # 2. 从 Campaign 名称中提取 ASIN 模式 (如 Auto_SP_B08N5WRWNW)
        matches = re.findall(r'[Bb][0-9][A-Za-z0-9]{8}', campaign_name)
        if matches:
            return matches[0].upper()

        # 3. 从 keyword / search_term 中尝试提取
        for key in ['keyword', 'search_term']:
            val = str(row.get(key, ''))
            matches = re.findall(r'[Bb][0-9][A-Za-z0-9]{8}', val)
            if matches:
                return matches[0].upper()

        return ''

    def _infer_ad_type(self, campaign_name: str, report_type: str) -> str:
        """根据 Campaign 名称推断广告类型"""
        name_lower = str(campaign_name).lower()
        if 'sb_' in name_lower or 'sponsored brands' in name_lower or 'sb ' in name_lower or '品牌' in name_lower:
            return 'SB'
        elif 'sd_' in name_lower or 'sponsored display' in name_lower or 'sd ' in name_lower or '展示' in name_lower:
            return 'SD'
        elif report_type.startswith('sb_'):
            return 'SB'
        elif report_type.startswith('sd_'):
            return 'SD'
        elif 'organic' in name_lower:
            return 'Organic'
        return 'SP'

    def build_analysis_context(self, parsed_reports: List[Dict]) -> str:
        """将解析后的报表数据构建成 LLM prompt 的上下文"""
        context = []
        total_spend = 0
        total_sales = 0
        total_orders = 0
        total_clicks = 0

        for report in parsed_reports:
            if not report.get('success'):
                continue
            data = report.get('data', [])
            if not data:
                continue

            report_type = report.get('report_type', 'unknown')
            context.append(f"\n=== {report_type} ({report.get('filename')}) ===")
            context.append(f"数据行数: {len(data)}")

            for row in data[:20]:  # 每份报表最多取20行
                row_str = ', '.join([f"{k}={v}" for k, v in row.items() if v and str(v) not in ('0.0', '0', '0.00', '')])
                if row_str:
                    context.append(row_str)

            # 计算汇总指标
            for row in data:
                total_spend += float(row.get('spend', 0) or 0)
                total_sales += float(row.get('sales', 0) or 0)
                total_orders += int(row.get('orders', 0) or 0)
                total_clicks += int(row.get('clicks', 0) or 0)

        # 添加汇总
        acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        summary = f"\n=== 汇总指标 ===\n总花费: ${total_spend:.2f}\n总销售额: ${total_sales:.2f}\n总订单: {total_orders}\n总点击: {total_clicks}\n整体ACOS: {acos:.1f}%\n"

        return '\n'.join(context) + summary
