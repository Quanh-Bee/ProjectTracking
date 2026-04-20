# 🎯 Face Tracking System - Hướng dẫn sử dụng

## 🚀 Cách chạy hệ thống

### **1. Chạy Camera + API (Khuyến nghị)**
```bash
python main.py
# Chọn option 3 (camera + API)
# Camera: hiển thị video với nhận diện
# API: http://localhost:5000 (dashboard)
```

### **2. Chỉ chạy Camera**
```bash
python run_camera.py
# Hoặc: python main.py -> chọn option 1
```

### **3. Chỉ chạy API Dashboard**
```bash
python main.py
# Chọn option 2
# Mở: http://localhost:5000
```

## 📸 Đăng ký người mới

### **Cách 1: Web Dashboard (Khuyến nghị)**
1. Mở http://localhost:5000
2. Cuộn xuống "Đăng ký người mới"
3. Nhập tên + upload 3 ảnh
4. Nhấn "Đăng ký người mới"
5. **Hệ thống tự động reload face encodings!**

### **Cách 2: Script**
```bash
python register_person.py
# Đặt ảnh vào known_faces/ trước
```

## 🛠️ Công cụ quản lý

### **Reset Database**
```bash
# Xóa hoàn toàn database
python tools/force_clear_database.py

# Reset từ ảnh trong known_faces/
python tools/reset_db_from_known_faces.py
```

### **Kiểm tra Camera**
```bash
python tools/check_camera.py
```

### **Phân tích Face Encodings**
```bash
python tools/compute_embedding_stats.py
```

### **Re-encode Face Encodings**
```bash
python tools/reencode_db_faces.py
```

## ⌨️ Phím tắt Camera

- **'q'**: Thoát
- **'r'**: Reset tracking
- **'l'**: Reload face encodings

## 📁 Cấu trúc thư mục

```
├── main.py                 # Entry point chính
├── run_camera.py          # Chạy camera riêng
├── register_person.py     # Đăng ký người từ ảnh
├── config.py              # Cấu hình hệ thống
├── app/                   # Core application
│   ├── api/routes.py      # REST API endpoints
│   ├── models/database.py # Database models
│   └── services/          # Business logic
├── templates/dashboard.html # Web dashboard
├── known_faces/           # Ảnh đăng ký người
├── tools/                 # Công cụ quản lý
└── database/attendance.db # SQLite database
```

## 🔧 Cấu hình

Chỉnh sửa `config.py`:
- `FACE_RECOGNITION_TOLERANCE`: Ngưỡng nhận diện (0.4)
- `CAMERA_INDEX`: Index camera (0)
- `CAMERA_WIDTH/HEIGHT`: Độ phân giải (640x480)

## 🐛 Troubleshooting

### **Camera không mở được:**
```bash
python tools/check_camera.py
# Thử các index khác: 0, 1, 2...
```

### **Không nhận diện được:**
1. Kiểm tra ảnh có khuôn mặt rõ ràng
2. Thử giảm threshold trong config.py
3. Nhấn 'l' để reload face encodings

### **Database lỗi:**
```bash
python tools/force_clear_database.py
# Reset hoàn toàn database
```

## 📊 Tính năng chính

- ✅ **Face Recognition** với facenet-pytorch
- ✅ **People Tracking** với YOLO + DeepSORT
- ✅ **Auto Attendance** logging
- ✅ **Web Dashboard** real-time
- ✅ **Multi-person support**
- ✅ **Auto-reload** face encodings
