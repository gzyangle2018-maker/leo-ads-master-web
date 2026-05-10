"""
Leo Ads Master - 12 Dimension Analysis Engine (v2.1)
"""
import re
from typing import List, Dict, Any, Tuple
import pandas as pd


class AdsAnalyzerEngine:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.acos_target = self.config.get('acos_target', 25)
        self.tacos_target = self.config.get('tacos_target', 12)
        self.budget_limit_pct = self.config.get('budget_limit_pct', 10)

    # ==================== 数据校验 ====================
    def validate_data(self, dfs: Dict[str, pd.DataFrame]) -> Tuple[bool, List[str], List[str]]:
        required = {
            'sp_search_term': 'SP搜索词报表',
            'sp_placement': 'Placement报表',
            'business_report': 'Business Reports',
            'campaign_summary': 'Campaign Summary'
        }
        optional = {
            'sb_search_term': 'SB搜索词报表',
            'sd_targeting': 'SD投放报表',
            'audience_amc': 'Audience/AMC报表',
            'sbv_video': 'SBV视频数据',
            'aba_search_term': 'ABA搜索词报表'
        }
        available = []
        missing = []
        for key, name in required.items():
            if key in dfs and not dfs[key].empty:
                available.append(name)
            else:
                missing.append(name)
        for key, name in optional.items():
            if key in dfs and not dfs[key].empty:
                available.append(name)
        usable = len([m for m in missing if m in required.values()]) < 2
        return usable, available, missing

    # ==================== 硬规则引擎 ====================
    def apply_budget_rules(self, acos_3d: float, current_budget: float) -> Tuple[float, str]:
        if acos_3d < 20:
            return current_budget * 2.0, f"近3天ACOS {acos_3d:.1f}% < 20%，预算+100%"
        elif acos_3d > 35:
            return current_budget * 0.5, f"近3天ACOS {acos_3d:.1f}% > 35%，预算-50%"
        return current_budget, "ACOS在20-35%区间，预算不变"

    def apply_bid_rules(self, acos: float, current_bid: float) -> Tuple[float, str]:
        if 0 <= acos <= 10:
            return current_bid + 0.2, f"ACOS {acos:.1f}% 0-10%，出价+0.2"
        elif 10 < acos <= 20:
            return current_bid + 0.1, f"ACOS {acos:.1f}% 10-20%，出价+0.1"
        elif 30 <= acos <= 40:
            return current_bid - 0.1, f"ACOS {acos:.1f}% 30-40%，出价-0.1"
        elif acos > 40:
            return current_bid - 0.2, f"ACOS {acos:.1f}% >40%，出价-0.2"
        return current_bid, f"ACOS {acos:.1f}% 在20-30%，出价不变"

    def apply_negative_rules(self, clicks: int, orders: int, is_core_keyword: bool = False) -> Tuple[str, str]:
        if clicks >= 10 and orders == 0:
            if is_core_keyword:
                return "待确认", "高相关核心词，需负责人确认后否定"
            return "否定", f"点击{clicks}次0转化，建议否定"
        return "保留", "未达否定阈值"

    def apply_b2b_rules(self, has_business_price: bool, keyword: str) -> Tuple[float, str]:
        if not has_business_price:
            return 0, "缺Business Price或阶梯价，先补Business Price & 阶梯价"
        kw_lower = keyword.lower()
        if any(x in kw_lower for x in ['bulk', 'pack', 'wholesale', 'commercial', 'industrial', 'multi']):
            return 50, "Bulk/多件装词 → 企业购溢价+50%"
        return 20, "通用/标准类词 → 企业购溢价+20%"

    # ==================== 问题分类诊断 ====================
    def diagnose(self, metrics: dict) -> Dict[str, Any]:
        main_issue = None
        sub_issues = []
        page_first = False
        acos = metrics.get('acos', 0)
        tacos = metrics.get('tacos', 0)
        ctr = metrics.get('ctr', 0)
        cvr = metrics.get('cvr', 0)
        unit_session_pct = metrics.get('unit_session_pct', 0)
        impressions = metrics.get('impressions', 0)
        clicks = metrics.get('clicks', 0)
        orders = metrics.get('orders', 0)
        spend = metrics.get('spend', 0)
        sales = metrics.get('sales', 0)
        budget = metrics.get('budget', 0)

        if impressions > 0 and spend < budget * 0.1:
            main_issue = "花费花不出去"
        elif clicks > 0 and orders == 0 and spend > 0:
            main_issue = "花费有但没转化"
        elif acos > self.acos_target * 1.5:
            main_issue = "ACOS失控"
        elif tacos > self.tacos_target:
            main_issue = "TACOS过高"
        elif acos > self.acos_target:
            main_issue = "ACOS偏高"
        else:
            main_issue = "表现正常，可寻求增量"

        if unit_session_pct < 8:
            sub_issues.append("页面转化差")
            page_first = True
        if ctr < 0.2 and impressions > 1000:
            sub_issues.append("点击率低，素材/排名待优化")
        if cvr < 5 and clicks > 50:
            sub_issues.append("转化率低，页面或词相关性待优化")
        if spend > sales * 0.5 and orders > 0:
            sub_issues.append("竞品ASIN吃预算")

        return {
            'main_issue': main_issue,
            'sub_issues': sub_issues,
            'page_first': page_first,
            'page_first_msg': "页面与报价优先，不做激进放量；广告只做防守性+精准收割操作。" if page_first else None
        }

    # ==================== 流量词架构（8层分层） ====================
    def build_traffic_tree(self, campaign_data: List[dict]) -> List[dict]:
        """构建流量词结构树：核心词→一级大词→二级大词→一级长尾→二级长尾→词根→品牌→活动"""
        tree = []
        for camp in campaign_data:
            kw = camp.get('keyword', '')
            if not kw:
                continue
            sv = str(camp.get('search_volume', '0'))
            try:
                sv_num = int(sv) if sv not in ('缺失', '', '-') else 0
            except Exception:
                sv_num = 0

            level = self._classify_traffic_level(kw, sv_num)
            acos = camp.get('acos_30d', 0)
            tree.append({
                'level': level,
                'keyword': kw,
                'source': 'SP搜索词',
                'intent': self.classify_intent(kw),
                'search_volume': sv if sv not in ('', '-') else '缺失',
                'aba_rank': str(camp.get('aba_rank', '缺失')),
                'acos': f"{acos:.1f}%",
                'action': '保持' if acos < 25 else ('优化' if acos < 40 else '否词/降竞价'),
                'orders': camp.get('orders', 0),
                'clicks': camp.get('clicks', 0),
                'campaign': camp.get('campaign', ''),
                'ad_group': camp.get('ad_group', ''),
                'ad_type': camp.get('ad_type', 'SP')
            })

        level_order = {
            '核心词': 0, '一级大词': 1, '二级大词': 2,
            '一级长尾词': 3, '二级长尾词': 4,
            '词根词': 5, '品牌词': 6, '活动词': 7
        }
        tree.sort(key=lambda x: (level_order.get(x['level'], 99), -(int(x['search_volume']) if str(x['search_volume']).isdigit() else 0)))
        return tree

    def _classify_traffic_level(self, keyword: str, search_volume: int) -> str:
        kw_lower = keyword.lower()
        words = kw_lower.split()

        # 品牌词
        brand_indicators = ['brand', 'official', 'original', 'genuine', 'authentic']
        if any(b in kw_lower for b in brand_indicators) or keyword.startswith('Brand_'):
            return '品牌词'

        # 活动词
        promo_indicators = ['deal', 'sale', 'discount', 'coupon', 'prime', 'promo', 'clearance', 'black friday', 'cyber monday']
        if any(p in kw_lower for p in promo_indicators):
            return '活动词'

        # 词根词（1-2个单词的短词）
        if len(words) <= 2 and search_volume >= 10000:
            return '词根词'

        # 按搜索量分层
        if search_volume >= 100000:
            return '核心词'
        elif search_volume >= 50000:
            return '一级大词'
        elif search_volume >= 10000:
            return '二级大词'
        elif search_volume >= 1000:
            return '一级长尾词'
        elif search_volume >= 100:
            return '二级长尾词'
        elif len(words) <= 2:
            return '词根词'
        else:
            return '二级长尾词'

    # ==================== 12维度分析（按广告活动分组，ACOS最高优先） ====================
    def analyze_12_dimensions(self, campaign_data: List[dict], metrics: dict, stage: str = 'growth') -> List[dict]:
        actions = []
        diagnosis = self.diagnose(metrics)

        stage_rules = {
            'new_product': {'budget_factor': 1.5, 'acos_tol': 35, 'bid_aggressive': True, 'focus': '数据积累'},
            'relaunch': {'budget_factor': 1.3, 'acos_tol': 30, 'bid_aggressive': True, 'focus': '拓量+控ACOS'},
            'growth': {'budget_factor': 1.2, 'acos_tol': 28, 'bid_aggressive': True, 'focus': '销量增长'},
            'profit': {'budget_factor': 0.9, 'acos_tol': 22, 'bid_aggressive': False, 'focus': '精准收割'},
            'clearance': {'budget_factor': 1.0, 'acos_tol': 40, 'bid_aggressive': False, 'focus': '快速出单'}
        }
        sr = stage_rules.get(stage, stage_rules['growth'])

        # 按广告活动分组，并按组内最高ACOS排序（ACOS高的组优先）
        groups = {}
        for camp in campaign_data:
            key = (camp.get('campaign', ''), camp.get('ad_group', ''))
            if key not in groups:
                groups[key] = []
            groups[key].append(camp)

        # 按组内最大ACOS降序排列
        sorted_groups = sorted(groups.items(), key=lambda x: max([c.get('acos_30d', 0) for c in x[1]]), reverse=True)

        for (campaign, ad_group), camps in sorted_groups:
            # 取该组的主要数据（用最高ACOS的代表）
            rep = max(camps, key=lambda c: c.get('acos_30d', 0))
            asin = rep.get('asin', '')
            ad_type = rep.get('ad_type', 'SP')
            current_budget = rep.get('budget', 0)
            acos_3d = rep.get('acos_3d', 0)
            acos_30d = rep.get('acos_30d', 0)
            current_bid = rep.get('bid', 0)
            clicks = rep.get('clicks', 0)
            orders = rep.get('orders', 0)
            keyword = rep.get('keyword', '')
            cvr = rep.get('cvr', 0)
            intent = self.classify_intent(keyword)

            # 1. 预算调整层
            base_budget, budget_reason = self.apply_budget_rules(acos_3d, current_budget)
            if sr['budget_factor'] != 1.0 and base_budget > current_budget:
                base_budget = current_budget * sr['budget_factor']
                budget_reason += f" | 阶段策略({sr['focus']})预算系数×{sr['budget_factor']}"
            if abs(base_budget - current_budget) > 0.01:
                is_add = base_budget > current_budget
                actions.append({
                    'priority': '高' if acos_3d < 20 or acos_3d > 35 else '中',
                    'layer': '1.预算调整层',
                    'category': '加法' if is_add else '减法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"预算${current_budget}/日 ACOS3d={acos_3d:.1f}%",
                    'action': '增加预算' if is_add else '减少预算',
                    'adjust_value': f"${current_budget:.2f} → ${base_budget:.2f}",
                    'reason': budget_reason,
                    'expected_impact': f"单量{'+30%' if is_add else '-15%'} | {sr['focus']}",
                    'exec_time': '立即'
                })

            # 2. 竞价调整层
            new_bid, bid_reason = self.apply_bid_rules(acos_30d, current_bid)
            if sr['bid_aggressive'] and new_bid > current_bid:
                new_bid = round(new_bid + 0.1, 2)
                bid_reason += " | 阶段策略加价+0.1"
            if abs(new_bid - current_bid) > 0.01:
                is_add = new_bid > current_bid
                actions.append({
                    'priority': '高',
                    'layer': '2.竞价调整层',
                    'category': '加法' if is_add else '减法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"出价${current_bid:.2f} ACOS30d={acos_30d:.1f}%",
                    'action': '提高出价' if is_add else '降低出价',
                    'adjust_value': f"${current_bid:.2f} → ${new_bid:.2f}",
                    'reason': bid_reason,
                    'expected_impact': f"{'抢排名' if is_add else '控ACOS'}",
                    'exec_time': '立即'
                })

            # 3. 加词层（精准/词组/广泛新增）
            if intent in ('产品适配/兼容意图(Compatibility)', '规格参数意图(Spec)', '场景/用途意图(Scenario)') and orders > 0:
                actions.append({
                    'priority': '中',
                    'layer': '3.精准/词组/广泛新增层',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"意图:{intent} 订单:{orders}",
                    'action': '新增Exact/Phrase',
                    'adjust_value': f"Phrase:{keyword} Exact:{keyword}",
                    'reason': f"高意图词已出单{orders}单，扩大匹配覆盖 | 阶段:{sr['focus']}",
                    'expected_impact': '增加精准流量入口',
                    'exec_time': '3天内'
                })

            # 4. 否词层
            neg_status, neg_reason = self.apply_negative_rules(clicks, orders, is_core_keyword=rep.get('is_core', False))
            if neg_status == "否定":
                actions.append({
                    'priority': '高',
                    'layer': '4.否词/否ASIN层',
                    'category': '减法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"点击{clicks}次 订单{orders}",
                    'action': '否定关键词',
                    'adjust_value': 'Negative Exact',
                    'reason': neg_reason,
                    'expected_impact': '减少无效花费',
                    'exec_time': '立即'
                })

            # 5. 拆精准层（词组/广泛 → 精准）
            if orders >= 3 and acos_30d < 20 and ('Broad' in campaign or 'Phrase' in campaign):
                actions.append({
                    'priority': '高',
                    'layer': '5.拆精准层（词组/广泛→精准）',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"ACOS{acos_30d:.1f}% 订单{orders} {campaign}组",
                    'action': '词组/广泛中拉出打精准',
                    'adjust_value': f"新建Exact组: {keyword.replace(' ','-')[:20]}",
                    'reason': f"高表现词(订单{orders},ACOS{acos_30d:.1f}%)必须从Broad/Phrase拉出单独收割 | One Keyword One Ad Group",
                    'expected_impact': '提升精准组ACOS控制',
                    'exec_time': '3天内'
                })

            # 6. 精准→词组/广泛（反向扩展）
            if orders >= 5 and acos_30d < 15 and 'Exact' in campaign:
                actions.append({
                    'priority': '中',
                    'layer': '6.精准→词组/广泛扩展层',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"ACOS{acos_30d:.1f}% 订单{orders} Exact组",
                    'action': '精准词扩展打词组和广泛',
                    'adjust_value': f"Phrase:{keyword} Broad:{keyword}*",
                    'reason': '高表现精准词可扩展匹配方式获取增量流量',
                    'expected_impact': '扩大流量覆盖同时保持ACOS',
                    'exec_time': '7天内'
                })

            # 7. 分流隔离层
            if 'Exact' in campaign and 'Broad' in str([c.get('campaign', '') for c in campaign_data]):
                actions.append({
                    'priority': '中',
                    'layer': '7.广泛/词组重构层',
                    'category': '减法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"Exact:{keyword} 存在Broad组",
                    'action': 'Broad组否定Exact',
                    'adjust_value': f"Negative Exact: {keyword}",
                    'reason': '已拉精准的词必须在Broad中否定Exact，避免互抢',
                    'expected_impact': '保护核心收割组不被污染',
                    'exec_time': '立即'
                })

            # 8. 广告位溢价层
            if acos_30d < 20 and orders >= 2:
                actions.append({
                    'priority': '中',
                    'layer': '8.广告位溢价层',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"ACOS{acos_30d:.1f}% 订单{orders}",
                    'action': 'Top位溢价',
                    'adjust_value': 'Top of Search +80% | Rest of Search +10% | Product Pages +20%',
                    'reason': '核心收割词必须抢Top位，拦截高意图流量',
                    'expected_impact': '提升Top位份额和转化率',
                    'exec_time': '立即'
                })

            # 9. 企业购层
            b2b_premium, b2b_reason = self.apply_b2b_rules(has_business_price=True, keyword=keyword)
            if b2b_premium > 0:
                actions.append({
                    'priority': '中',
                    'layer': '9.企业购溢价层',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"词:{keyword}",
                    'action': '加企业购',
                    'adjust_value': f"+{b2b_premium}%",
                    'reason': b2b_reason,
                    'expected_impact': '提升B2B订单占比',
                    'exec_time': '立即'
                })

            # 10. 隐形词挖掘层
            if orders >= 2 and acos_30d < 25:
                actions.append({
                    'priority': '中',
                    'layer': '10.隐形词挖掘层',
                    'category': '加法',
                    'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                    'target': keyword or '-',
                    'current_data': f"ACOS{acos_30d:.1f}% 订单{orders}",
                    'action': '挖掘隐形词',
                    'adjust_value': f"Search Term Report中找{keyword}相关变体 → 新增Exact测试",
                    'reason': '高表现词周边存在大量未投放的隐形搜索词',
                    'expected_impact': '扩大高转化词覆盖',
                    'exec_time': '7天内'
                })

            # 11. 品牌词加减层
            if any(b in keyword.lower() for b in ['brand', 'official', 'original']):
                if acos_30d < 15:
                    actions.append({
                        'priority': '中',
                        'layer': '11.品牌词加减层',
                        'category': '加法',
                        'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                        'target': keyword or '-',
                        'current_data': f"ACOS{acos_30d:.1f}%",
                        'action': '品牌词加预算/加竞价',
                        'adjust_value': '预算+20% 竞价+0.1',
                        'reason': '品牌词ACOS优秀，加大防守力度',
                        'expected_impact': '保护品牌流量不被竞品抢夺',
                        'exec_time': '立即'
                    })
                elif acos_30d > 40:
                    actions.append({
                        'priority': '高',
                        'layer': '11.品牌词加减层',
                        'category': '减法',
                        'ad_type': ad_type, 'campaign': campaign, 'ad_group': ad_group,
                        'target': keyword or '-',
                        'current_data': f"ACOS{acos_30d:.1f}%",
                        'action': '品牌词减预算/否词',
                        'adjust_value': '预算-30% 或 Negative Exact',
                        'reason': '品牌词ACOS异常高，检查是否被竞品跟卖或页面问题',
                        'expected_impact': '控花费，先排查页面',
                        'exec_time': '立即'
                    })

            # 12. 结构调整层（每个ASIN只输出一次）
            if len([a for a in actions if a['layer'] == '12.SP/SB/SD结构调整层']) == 0:
                structure_map = {
                    'new_product': 'SP=70% Auto/Broad拓量+Exact测试 | SB=20% 品牌防御 | SD=10% 浏览再营销',
                    'relaunch': 'SP=60% Broad/Phrase拓量+Exact收割 | SB=25% 品牌+竞品 | SD=15% 再营销+兴趣拓新',
                    'growth': 'SP=55% 收割为主+少量拓量 | SB=25% 品牌防御 | SD=20% 再营销+兴趣拓新',
                    'profit': 'SP=50% Exact精准收割为主 | SB=30% 品牌防御+高ROAS词 | SD=20% 高意图再营销',
                    'clearance': 'SP=70% Broad低价跑量 | SB=15% 低价引流 | SD=15% 价格敏感人群'
                }
                actions.append({
                    'priority': '中',
                    'layer': '12.SP/SB/SD结构调整层',
                    'category': '加法' if sr['budget_factor'] >= 1.0 else '减法',
                    'ad_type': 'All', 'campaign': '整体结构', 'ad_group': '-',
                    'target': '-',
                    'current_data': f"阶段:{stage}",
                    'action': '重构预算比例',
                    'adjust_value': structure_map.get(stage, structure_map['growth']),
                    'reason': f"根据阶段策略({sr['focus']})调整SP/SB/SD预算分配",
                    'expected_impact': '结构匹配阶段目标',
                    'exec_time': '7天内'
                })

        return actions

    def classify_intent(self, keyword: str) -> str:
        kw_lower = keyword.lower()
        if any(w in kw_lower for w in ['best', 'how to', 'what is', 'which', 'is ', 'compatible', 'does ', 'for ']):
            return '问答意图(QA)'
        if any(w in kw_lower for w in ['vs', 'versus', 'alternative', 'compared to', 'better than']):
            return '对比意图(Comparison)'
        if any(w in kw_lower for w in ['office', 'home', 'travel', 'desk', 'setup', 'gift', 'kitchen', 'outdoor']):
            return '场景/用途意图(Scenario)'
        if any(w in kw_lower for w in ['ft', 'inch', 'awg', 'v', 'w', 'a', 'mah', 'gb', 'hz', 'oz', 'kg', 'ml']):
            return '规格参数意图(Spec)'
        if any(w in kw_lower for w in ['durable', 'heavy duty', 'fast', 'premium', 'safe', 'best', 'quality']):
            return '痛点/价值意图(Pain/Value)'
        if any(w in kw_lower for w in ['brand', 'original', 'genuine']):
            return '品牌/对标意图(Brand)'
        if any(w in kw_lower for w in ['your brand', 'official']):
            return '防守意图(Defense)'
        if any(w in kw_lower for w in ['for ', 'compatible', 'replacement', 'adapter']):
            return '产品适配/兼容意图(Compatibility)'
        return '产品适配/兼容意图(Compatibility)'

    def generate_three_plans(self, metrics: dict, stage: str = 'growth') -> dict:
        current_acos = metrics.get('acos', 0)
        stage_mod = {
            'new_product':   {'budget_pct': 60, 'acos_shift': +8,  'order_boost': '+15~+30'},
            'relaunch':      {'budget_pct': 40, 'acos_shift': +5,  'order_boost': '+20~+40'},
            'growth':        {'budget_pct': 30, 'acos_shift': +3,  'order_boost': '+25~+45'},
            'profit':        {'budget_pct': 10, 'acos_shift': -3,  'order_boost': '+5~+15'},
            'clearance':     {'budget_pct': 50, 'acos_shift': +12, 'order_boost': '+30~+60'}
        }
        sm = stage_mod.get(stage, stage_mod['growth'])

        def acos_range(base_low, base_high):
            return f"{max(10, base_low + sm['acos_shift']):.0f}%~{max(15, base_high + sm['acos_shift']):.0f}%"

        return {
            'conservative': {
                'budget_change': f"总预算{'+'+str(sm['budget_pct']//3)+'%' if sm['budget_pct']>0 else '不变'}，组间转移",
                'bid_strategy': '按硬规则微调，阶段保守执行',
                'estimated_order_increase': sm['order_boost'].split('~')[0] + '%~' + str(int(float(sm['order_boost'].split('~')[1].replace('+','')) * 0.6)),
                'acos_range': acos_range(max(15, current_acos-5), max(20, current_acos)),
                'fallback_period': '7天',
                'suitable': '资金紧张/页面一般/新品试水'
            },
            'balanced': {
                'budget_change': f"总预算+{sm['budget_pct']}%，高绩效组加预算",
                'bid_strategy': '按硬规则+Top位溢价+阶段加词',
                'estimated_order_increase': sm['order_boost'] + '%',
                'acos_range': acos_range(max(18, current_acos-3), min(35, current_acos+8)),
                'fallback_period': '14天',
                'suitable': '正常运营/追求增长/阶段主方案'
            },
            'aggressive': {
                'budget_change': f"总预算+{int(sm['budget_pct']*1.5)}%，新开拓量组+品牌防御",
                'bid_strategy': '提高和降低模式+高溢价+SBV放量',
                'estimated_order_increase': '+' + str(int(float(sm['order_boost'].split('~')[1].replace('+','')) * 1.5)) + '~+' + str(int(float(sm['order_boost'].split('~')[1].replace('+','')) * 2.0)) + '%',
                'acos_range': acos_range(max(22, current_acos), min(40, current_acos+12)),
                'fallback_period': '21天',
                'suitable': '冲排名/大促前/库存充足/清库存'
            }
        }

    def generate_monitor_plan(self, metrics: dict) -> List[dict]:
        return [
            {'target': '核心词ACOS', 'metric': 'ACOS', 'threshold': f'> {self.acos_target}%', 'trigger': '降价 -0.2', 'window': '3天内'},
            {'target': '核心词ACOS', 'metric': 'ACOS', 'threshold': f'< {self.acos_target * 0.6:.0f}%', 'trigger': '提价 +0.1', 'window': '3天内'},
            {'target': 'Top位CTR', 'metric': 'CTR', 'threshold': '< 0.3%', 'trigger': '审查素材/页面', 'window': '48小时'},
            {'target': '宽泛匹配ACOS', 'metric': 'ACOS', 'threshold': '> 40%', 'trigger': '否词+降预算', 'window': '3天内'},
            {'target': '企业购订单', 'metric': 'B2B占比', 'threshold': '< 8%', 'trigger': '降B2B溢价', 'window': '7天内'},
            {'target': '新增Exact组', 'metric': '订单数', 'threshold': '= 0（3天）', 'trigger': '否掉或降出价', 'window': '3天内'},
            {'target': 'RUFUS-QA组', 'metric': 'ACOS', 'threshold': '> 45%', 'trigger': '否词+降竞价', 'window': '5天内'},
            {'target': 'RUFUS-QA组', 'metric': 'CTR', 'threshold': '> 1.5%', 'trigger': '加大预算', 'window': '5天内'},
        ]
