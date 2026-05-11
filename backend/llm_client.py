"""
Leo Ads Master - LLM Client
支持多厂商大模型接入与连通性测试
"""
import os
import json
import urllib.request
import urllib.error
import ssl
from typing import Dict, List, Optional, Tuple


class LLMClient:
    """统一大模型调用客户端"""

    PROVIDERS = {
        'openai': {
            'name': 'OpenAI',
            'base_url': 'https://api.openai.com/v1',
            'models': ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
            'default_model': 'gpt-4o',
            'key_prefix': 'sk-',
            'chat_endpoint': '/chat/completions',
        },
        'claude': {
            'name': 'Anthropic Claude',
            'base_url': 'https://api.anthropic.com',
            'models': ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-sonnet-20240229', 'claude-3-haiku-20240307'],
            'default_model': 'claude-3-5-sonnet-20241022',
            'key_prefix': 'sk-ant-',
            'chat_endpoint': '/v1/messages',
            'auth_header': 'x-api-key',
            'version_header': 'anthropic-version:2023-06-01',
        },
        'azure': {
            'name': 'Azure OpenAI',
            'base_url': 'https://{your-resource}.openai.azure.com/openai/deployments/{your-deployment}',
            'models': ['gpt-4o', 'gpt-4', 'gpt-35-turbo'],
            'default_model': 'gpt-4o',
            'key_prefix': '',
            'chat_endpoint': '/chat/completions?api-version=2024-02-01',
            'auth_header': 'api-key',
        },
        'zhipu': {
            'name': '智谱AI (GLM)',
            'base_url': 'https://open.bigmodel.cn/api/paas/v4',
            'models': ['glm-4', 'glm-4-air', 'glm-4-flash', 'glm-4-plus'],
            'default_model': 'glm-4',
            'key_prefix': '',
        },
        'qwen': {
            'name': '通义千问 (Aliyun)',
            'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'models': ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-coder-plus'],
            'default_model': 'qwen-max',
            'key_prefix': 'sk-',
        },
        'deepseek': {
            'name': 'DeepSeek',
            'base_url': 'https://api.deepseek.com/v1',
            'models': ['deepseek-chat', 'deepseek-reasoner', 'deepseek-coder'],
            'default_model': 'deepseek-chat',
            'key_prefix': 'sk-',
        },
        'moonshot': {
            'name': 'Moonshot (Kimi)',
            'base_url': 'https://api.moonshot.cn/v1',
            'models': ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
            'default_model': 'moonshot-v1-8k',
            'key_prefix': 'sk-',
        },
        'baidu': {
            'name': '百度文心一言',
            'base_url': 'https://qianfan.baidubce.com/v2',
            'models': ['ernie-4.0-turbo-8k', 'ernie-3.5-8k', 'ernie-speed-128k'],
            'default_model': 'ernie-4.0-turbo-8k',
            'key_prefix': '',
        },
        'gemini': {
            'name': 'Google Gemini',
            'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
            'models': ['gemini-2.5-pro-preview-03-25', 'gemini-2.0-flash', 'gemini-1.5-pro'],
            'default_model': 'gemini-2.5-pro-preview-03-25',
            'key_prefix': '',
        },
        'grok': {
            'name': 'xAI Grok',
            'base_url': 'https://api.x.ai/v1',
            'models': ['grok-3', 'grok-3-mini', 'grok-2'],
            'default_model': 'grok-3',
            'key_prefix': '',
        },
        'cohere': {
            'name': 'Cohere',
            'base_url': 'https://api.cohere.ai/v1',
            'models': ['command-r-plus', 'command-r', 'command'],
            'default_model': 'command-r-plus',
            'key_prefix': '',
        },
        'openrouter': {
            'name': 'OpenRouter',
            'base_url': 'https://openrouter.ai/api/v1',
            'models': ['openrouter/auto', 'anthropic/claude-3.5-sonnet', 'google/gemini-2.5-pro-preview'],
            'default_model': 'openrouter/auto',
            'key_prefix': '',
        },
        'siliconflow': {
            'name': 'SiliconFlow',
            'base_url': 'https://api.siliconflow.cn/v1',
            'models': ['deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1', 'Qwen/Qwen2.5-72B-Instruct'],
            'default_model': 'deepseek-ai/DeepSeek-V3',
            'key_prefix': '',
        },
    }

    def __init__(self, provider: str = 'openai', api_key: str = '',
                 base_url: str = '', model: str = '', timeout: int = 30):
        self.provider = provider
        self.api_key = api_key
        self.timeout = timeout
        cfg = self.PROVIDERS.get(provider, self.PROVIDERS['openai'])
        self.base_url = (base_url or cfg['base_url']).rstrip('/')
        self.model = model or cfg.get('default_model', 'gpt-4o')
        self._cfg = cfg

    def _request(self, endpoint: str, payload: dict, headers: dict) -> Tuple[bool, str, dict]:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                return True, '', body
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                err_msg = err_body.get('error', {}).get('message', str(e))
            except Exception:
                err_msg = f"HTTP {e.code}: {e.reason}"
            return False, err_msg, {}
        except Exception as e:
            return False, str(e), {}

    def test_connection(self) -> Tuple[bool, str]:
        """测试连接，返回 (success, message)"""
        if not self.api_key:
            return False, 'API Key 不能为空'
        if self.provider == 'claude':
            return self._test_claude()
        elif self.provider == 'baidu':
            return self._test_baidu()
        else:
            return self._test_openai_compatible()

    def _test_openai_compatible(self) -> Tuple[bool, str]:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': '你好，请回复"连接成功"'}],
            'max_tokens': 20,
            'temperature': 0.1,
        }
        endpoint = self._cfg.get('chat_endpoint', '/chat/completions')
        ok, err, body = self._request(endpoint, payload, headers)
        if not ok:
            return False, f'连接失败: {err}'
        try:
            choices = body.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '')
                return True, f'连接成功！模型响应: {content[:60]}'
            return True, '连接成功（无内容返回）'
        except Exception as e:
            return True, f'连接成功但解析响应异常: {e}'

    def _test_claude(self) -> Tuple[bool, str]:
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01'
        }
        payload = {
            'model': self.model,
            'max_tokens': 20,
            'messages': [{'role': 'user', 'content': '你好，请回复"连接成功"'}]
        }
        ok, err, body = self._request('/v1/messages', payload, headers)
        if not ok:
            return False, f'连接失败: {err}'
        try:
            content = body.get('content', [{}])[0].get('text', '')
            return True, f'连接成功！模型响应: {content[:60]}'
        except Exception as e:
            return True, f'连接成功但解析响应异常: {e}'

    def _test_baidu(self) -> Tuple[bool, str]:
        # 百度文心使用 Bearer token（Access Token 方式更复杂，这里简化测试）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': '你好'}],
            'max_tokens': 20,
        }
        ok, err, body = self._request('/chat/completions', payload, headers)
        if not ok:
            return False, f'连接失败: {err}'
        try:
            content = body.get('choices', [{}])[0].get('message', {}).get('content', '')
            return True, f'连接成功！模型响应: {content[:60]}'
        except Exception as e:
            return True, f'连接成功但解析响应异常: {e}'

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2000) -> Tuple[bool, str]:
        """通用对话接口，返回 (success, content_or_error)"""
        if self.provider == 'claude':
            return self._chat_claude(messages, temperature, max_tokens)
        return self._chat_openai_compatible(messages, temperature, max_tokens)

    def _chat_openai_compatible(self, messages, temperature, max_tokens):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        endpoint = self._cfg.get('chat_endpoint', '/chat/completions')
        ok, err, body = self._request(endpoint, payload, headers)
        if not ok:
            return False, err
        try:
            return True, body['choices'][0]['message']['content']
        except Exception as e:
            return False, f'解析失败: {e}'

    def _chat_claude(self, messages, temperature, max_tokens):
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01'
        }
        payload = {
            'model': self.model,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'messages': messages
        }
        ok, err, body = self._request('/v1/messages', payload, headers)
        if not ok:
            return False, err
        try:
            return True, body['content'][0]['text']
        except Exception as e:
            return False, f'解析失败: {e}'
