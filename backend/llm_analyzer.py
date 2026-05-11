"""
Leo Ads Master - LLM Analyzer Module
将报表数据发送给LLM进行智能分析
"""
import json
import traceback
from typing import Dict, List, Any

from llm_client import LLMClient


class LLMAnalyzer:
    """LLM智能分析器：将报表数据发送给大模型进行深度分析"""

    def __init__(self, provider: str = 'openai', api_key: str = '',
                 base_url: str = '', model: str = ''):
        self.client = LLMClient(provider=provider, api_key=api_key,
                                 base_url=base_url, model=model)

    def analyze_reports(self, context: str, metrics: dict, stage: str = 'growth',
                        asin: str = '') -> Dict[str, Any]:
        """调用LLM分析报表数据"""
        prompt = self._build_analysis_prompt(context, metrics, stage, asin)
        ok, result = self.client.chat(messages=[
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=4000)

        if not ok:
            return {'success': False, 'error': f'LLM调用失败: {result}', 'raw': result}

        # 解析LLM返回的结果
        parsed = self._parse_llm_response(result)
        return {'success': True, **parsed}

    def _get_system_prompt(self) -> str:
        """系统提示词"""
        return """你是亚马逊广告顶级优化专家，擅长基于真实广告报表数据进行深度分析。

你必须严格基于用户提供的真实报表数据进行分析，不要编造数据。
输出必须是结构化的JSON格式，包含以下字段：

{
  "diagnosis": {
    "main_issue": "主问题描述",
    "sub_issues": ["次问题1", "次问题2"],
    "page_first": true/false,
    "page_first_msg": "页面优化建议（如适用）"
  },
  "traffic_tree": [
    {
      "level": "核心词/一级大词/二级大词/一级长尾词/二级长尾词/词根词/品牌词/活动词",
      "keyword": "关键词",
      "source": "来源报表类型",
      "intent": "意图分类",
      "search_volume": "搜索量",
      "aba_rank": "ABA排名",
      "acos": "ACOS百分比",
      "action": "建议动作",
      "orders": 订单数,
      "clicks": 点击数,
      "campaign": "Campaign名称",
      "ad_group": "广告组名称",
      "ad_type": "SP/SB/SD"
    }
  ],
  "actions": [
    {
      "priority": "高/中/低",
      "layer": "1.预算调整层/2.竞价调整层/3.加词层/4.否词层/5.拆精准层/6.扩展层/7.重构层/8.溢价层/9.B2B层/10.隐形词层/11.品牌词层/12.结构调整层",
      "category": "加法/减法/保持",
      "ad_type": "SP/SB/SD/All",
      "campaign": "Campaign名称",
      "ad_group": "广告组名称",
      "target": "目标关键词",
      "current_data": "当前数据描述",
      "action": "具体动作",
      "adjust_value": "调整值",
      "reason": "原因",
      "expected_impact": "预期影响",
      "exec_time": "执行时间"
    }
  ],
  "today_add": [同上actions格式, 只包含"加法"类别],
  "today_sub": [同上actions格式, 只包含"减法"类别],
  "monitor_plan": [
    {
      "target": "监控目标",
      "metric": "监控指标",
      "threshold": "阈值",
      "trigger": "触发动作",
      "window": "时间窗口"
    }
  ],
  "three_plans": {
    "conservative": {"budget_change": "...", "bid_strategy": "...", "estimated_order_increase": "...", "acos_range": "...", "fallback_period": "...", "suitable": "..."},
    "balanced": {...},
    "aggressive": {...}
  }
}

分析原则：
1. 严格基于真实数据，不编造数字
2. 按12维度输出具体可执行动作
3. 量化到具体的USD金额和百分比
4. 区分加法（增加预算/竞价/加词）和减法（降低预算/竞价/否词）
5. 标注优先级和执行时间
"""

    def _build_analysis_prompt(self, context: str, metrics: dict, stage: str, asin: str) -> str:
        """构建分析请求prompt"""
        stage_map = {
            'new_product': '推新品（预算激进，关注数据积累）',
            'relaunch': '老品重推（平衡ACOS与单量）',
            'growth': '销量增长（接受短期ACOS上升）',
            'profit': '保利润（精准收割为主）',
            'clearance': '清库存（低利润跑量）'
        }

        prompt = f"""请基于以下真实广告报表数据进行12维度深度分析。

目标ASIN: {asin or '未指定'}
当前阶段: {stage_map.get(stage, stage)}
目标指标: ACOS={metrics.get('acos', 25)}%, TACOS={metrics.get('tacos', 12)}%

=== 报表数据 ===
{context}

请输出严格的JSON格式分析结果，确保：
1. 所有数据来自真实报表，不编造
2. actions列表包含12个维度的分析
3. 每个action包含priority、layer、category、ad_type、campaign、ad_group、target、current_data、action、adjust_value、reason、expected_impact、exec_time
"""
        return prompt

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM返回的JSON"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取JSON块
        import re
        # 匹配 ```json ... ``` 或 ``` ... ```
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试从文本中提取JSON
        try:
            start = response.index('{')
            end = response.rindex('}') + 1
            return json.loads(response[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        # 解析失败，返回原始文本
        return {'raw_response': response, 'error': '无法解析JSON'}

    def build_campaign_data_from_reports(self, parsed_reports: List[Dict]) -> List[Dict]:
        """从解析的报表构建campaign级别数据"""
        from report_parser import ReportParser
        parser = ReportParser()
        return parser.extract_campaign_data(parsed_reports)
