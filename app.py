import cv2
import numpy as np
import base64
from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from datetime import datetime
import pytz


app = Flask(__name__)
CORS(app)
app.debug = True  # 启用调试模式

# 上传二维码图片并识别内容
@app.route('/upload-qr', methods=['POST'])
def upload_qr():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未检测到文件'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400

        # 读取图片为OpenCV格式
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'success': False, 'message': '图片读取失败'}), 400

        # 优化1：尝试多种预处理（灰度、锐化、自适应阈值、放大、旋转）
        def try_decode(img):
            detector = cv2.QRCodeDetector()
            data, points, _ = detector.detectAndDecode(img)
            return data

        # 1. 原图直接识别
        data = try_decode(img)
        if not data:
            # 2. 灰度
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            data = try_decode(gray)
        if not data:
            # 3. 自适应阈值
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10)
            data = try_decode(th)
        if not data:
            # 4. 锐化
            kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
            sharp = cv2.filter2D(img, -1, kernel)
            data = try_decode(sharp)
        if not data:
            # 5. 放大（插值）
            h, w = img.shape[:2]
            if max(h, w) < 600:
                scale = 600.0 / max(h, w)
                big = cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
                data = try_decode(big)
        if not data:
            # 6. 旋转尝试
            for angle in [15, -15, 30, -30]:
                h, w = img.shape[:2]
                M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
                rot = cv2.warpAffine(img, M, (w, h), borderValue=(255,255,255))
                data = try_decode(rot)
                if data:
                    break

        if data:
            return jsonify({'success': True, 'qrContent': data, 'message': '识别成功'})
        else:
            return jsonify({'success': False, 'message': '未识别到二维码，建议图片更清晰或正对拍摄'}), 200
    except Exception as e:
        print(f"Error in upload_qr: {str(e)}")
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'}), 500

# 添加路由调试
@app.route('/')
def home():
    # 打印所有注册的路由
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify({
        "message": "QR Code Server is running",
        "registered_routes": routes
    })

@app.route('/verify-qr', methods=['POST'])
def verify_qr():
    print("verify_qr endpoint called")  # 添加调试日志
    print("Request data:", request.get_json())  # 打印请求数据
    try:
        data = request.get_json()
        if not data or 'qrContent' not in data:
            return jsonify({
                'success': False,
                'message': '无效的请求数据'
            }), 400

        qr_content = data['qrContent']
        print(f"Processing QR content: {qr_content}")  # 添加调试日志
        
        # 验证二维码格式
        if 'checkwork|id=' in qr_content:
            parts = qr_content.split('&')
            required_params = ['id=', 'siteId=', 'createTime=', 'classLessonId=']
            
            if all(any(param in part for part in parts) for param in required_params):
                return jsonify({
                    'success': True,
                    'message': '验证成功'
                })
        
        return jsonify({
            'success': False,
            'message': '无效的二维码格式'
        }), 400

    except Exception as e:
        print(f"Error in verify_qr: {str(e)}")  # 错误日志
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

@app.route('/generate-qr', methods=['POST'])
def generate_qr():
    print("generate_qr endpoint called")  # 添加调试日志
    print("Request data:", request.get_json())  # 打印请求数据
    try:
        data = request.get_json()
        if not data or 'baseString' not in data:
            return jsonify({
                'success': False,
                'message': '无效的请求数据'
            }), 400

        base_string = data['baseString']
        print(f"Processing base string: {base_string}")  # 添加调试日志
        
        # 解析原始字符串
        prefix = base_string.split('&')[0]
        parts = base_string.split('&')[1:]
        params = {}
        
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                params[key] = value
        
        # 更新时间戳为北京时间
        beijing_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(beijing_tz)
        params['createTime'] = current_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        
        # 重新组装字符串
        new_string = prefix + '&' + '&'.join([f"{k}={v}" for k, v in params.items()])
        
        return jsonify({
            'success': True,
            'qrContent': new_string,
            'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        })

    except Exception as e:
        print(f"Error in generate_qr: {str(e)}")  # 错误日志
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

# 添加错误处理器
@app.errorhandler(404)
def not_found_error(error):
    print(f"404 error: {request.url}")  # 打印 404 错误的 URL
    return jsonify({
        'success': False,
        'message': f'找不到请求的URL: {request.url}'
    }), 404

@app.errorhandler(Exception)
def handle_exception(error):
    print(f"Unhandled exception: {str(error)}")  # 打印未处理的异常
    return jsonify({
        'success': False,
        'message': f'服务器错误: {str(error)}'
    }), 500

if __name__ == '__main__':
    print("Starting QR Code Server on port 8000...")
    print("Debug mode enabled")
    print("Available routes:")
    for rule in app.url_map.iter_rules():
        print(f"Route: {rule}, Methods: {rule.methods}")
    app.run(host='0.0.0.0', port=8000, debug=True)