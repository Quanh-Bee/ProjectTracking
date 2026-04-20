import os
from datetime import timedelta

class Config:
    """Cấu hình chung cho hệ thống"""
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "attendance.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Face Recognition
    KNOWN_FACES_DIR = 'known_faces'
    FACE_RECOGNITION_TOLERANCE = 0.4
    FACE_RECOGNITION_MODEL = 'hog'  # hoặc 'cnn' cho độ chính xác cao hơn hog
    
    # Tracking
    YOLO_MODEL_PATH = 'yolov8n.pt'
    # YOLO_MODEL_PATH = 'person.pt'
    DEEPSORT_MAX_AGE = 30
    TRACKING_CONFIDENCE_THRESHOLD = 0.5
    
    # Attendance
    CHECKOUT_TIMEOUT = 10  # giây
    UNKNOWN_PERSON_LABEL = 'Unknown'
    
    # Camera
    CAMERA_INDEX = 0  # 0 cho webcam mặc định
    CAMERA_WIDTH = 640
    CAMERA_HEIGHT = 480
    CAMERA_FPS = 30
    
    # API
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    API_HOST = '0.0.0.0'
    API_PORT = 5000
    DEBUG = True
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/system.log'
    
    # Dashboard
    DASHBOARD_REFRESH_INTERVAL = 5000  # milliseconds
    
    @staticmethod
    def init_app(app):
        """Khởi tạo ứng dụng với cấu hình"""
        pass

class DevelopmentConfig(Config):
    """Cấu hình cho môi trường phát triển"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Cấu hình cho môi trường sản xuất"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    FACE_RECOGNITION_MODEL = 'hog'  # Sử dụng HOG cho local
    
    # Local database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "attendance.db")}'
    
    # Local API settings
    API_HOST = '127.0.0.1'
    API_PORT = int(os.environ.get('PORT', 5000))
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'local-secret-key'
    
    # Performance
    CAMERA_FPS = 30  # FPS cho local
    FACE_RECOGNITION_TOLERANCE = 0.6  # Tolerance cho local

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
