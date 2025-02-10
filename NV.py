from flask import Flask, request, Response, stream_with_context
import requests
import json
import re

app = Flask(__name__)

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    user_data = request.json
    
    if 'messages' in user_data:
        cleaned_messages = []
        for msg in user_data['messages']:
            content = msg.get('content', '')
            
            # Handle file content
            if isinstance(content, list):
                cleaned_msg = msg.copy()
                cleaned_msg['content'] = content
                cleaned_messages.append(cleaned_msg)
            else:
                cleaned_content = re.sub(r'<think>.*?</think>\s*\n*', '', content, flags=re.DOTALL)
                cleaned_msg = msg.copy()
                cleaned_msg['content'] = cleaned_content.strip()
                cleaned_messages.append(cleaned_msg)
                
        user_data['messages'] = cleaned_messages
    
    headers = {
        "Authorization": request.headers.get('Authorization'),
        "Content-Type": "application/json"
    }
    
    user_data['stream'] = True
    
    response = requests.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        json=user_data,
        headers=headers,
        stream=True
    )
    
    def generate():
        is_first_reasoning = True  
        last_was_reasoning = False 
        
        for line in response.iter_lines():
            if line:
                json_str = line.decode('utf-8').replace('data: ', '')
                
                if json_str == '[DONE]':
                    if last_was_reasoning:
                        modified_data = {
                            'choices': [{
                                'delta': {
                                    'content': "</think>"
                                }
                            }]
                        }
                        yield f"data: {json.dumps(modified_data)}\n\n"
                    yield 'data: [DONE]\n\n'
                    break
                
                try:
                    response_data = json.loads(json_str)
                    if 'choices' in response_data and response_data['choices']:
                        choice = response_data['choices'][0]
                        if 'delta' in choice:
                            delta = choice['delta']
                            
                            reasoning = delta.get('reasoning_content', '')
                            if reasoning:
                                if is_first_reasoning:
                                    modified_data = {
                                        'choices': [{
                                            'delta': {
                                                'content': "<think>"
                                            }
                                        }]
                                    }
                                    yield f"data: {json.dumps(modified_data)}\n\n"
                                    is_first_reasoning = False
                                
                                modified_data = {
                                    'choices': [{
                                        'delta': {
                                            'content': reasoning
                                        }
                                    }]
                                }
                                yield f"data: {json.dumps(modified_data)}\n\n"
                                last_was_reasoning = True
                            
                            content = delta.get('content', '')
                            if content:
                                if last_was_reasoning:
                                    modified_data = {
                                        'choices': [{
                                            'delta': {
                                                'content': "</think>\n\n"
                                            }
                                        }]
                                    }
                                    yield f"data: {json.dumps(modified_data)}\n\n"
                                    last_was_reasoning = False
                                yield f"data: {json_str}\n\n"
                            
                            if not (reasoning or content):
                                yield f"data: {json_str}\n\n"
                        else:
                            yield f"data: {json_str}\n\n"
                    else:
                        yield f"data: {json_str}\n\n"
                        
                except json.JSONDecodeError:
                    yield f"data: {json_str}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9003)
