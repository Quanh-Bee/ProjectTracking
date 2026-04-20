# Face Recognition & People Tracking System

Hệ thống nhận diện khuôn mặt và theo dõi người tự động, tích hợp chức năng chấm công thời gian thực thông qua camera.

## Tác giả

Đinh Thị Quỳnh Anh
GitHub: https://github.com/Quanh-Bee/ProjectTracking.git

---

## Tính năng chính

* Nhận diện khuôn mặt: Tự động nhận diện người dùng đã đăng ký
* Tracking người (Real-time): Theo dõi chuyển động của người trong video
* Chấm công tự động: Ghi nhận thời gian vào/ra tự động
* Web Dashboard: Giao diện web để quản lý và thống kê

---

## Cài đặt hệ thống

### Yêu cầu

* Python 3.8 trở lên
* Webcam hoặc Camera

---

### Bước 1: Clone repository

```bash
git clone https://github.com/Quanh-Bee/ProjectTracking.git
cd ProjectTracking
```

---

### Bước 2: Tạo môi trường ảo (khuyến nghị)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

---

### Bước 3: Cài đặt thư viện

```bash
pip install -r requirements.txt
```

---

### Bước 4: Cài đặt PyTorch & FaceNet (tùy chọn)

```bash
# CPU
pip install torch torchvision
pip install facenet-pytorch

# GPU (nếu có)
pip install torch --index-url https://download.pytorch.org/whl/cu117
pip install facenet-pytorch
```

---

## Hướng dẫn sử dụng

### Chạy hệ thống

```bash
python main.py
```

Sau khi chạy:

* Camera window: Hiển thị video với nhận diện và tracking
* Web Dashboard: Truy cập tại http://localhost:5000

---

### Phím tắt

| Phím | Chức năng                |
| ---- | ------------------------ |
| q    | Thoát hệ thống           |
| r    | Reset tracking           |
| l    | Reload dữ liệu khuôn mặt |

---

## Đăng ký người dùng

### Cách 1: Qua Web Dashboard

1. Truy cập http://localhost:5000
2. Chọn "Đăng ký người mới"
3. Nhập tên và upload 1–3 ảnh
4. Nhấn "Đăng ký"

Yêu cầu ảnh:

* Khuôn mặt rõ ràng
* Nhìn thẳng
* Ánh sáng tốt

---

### Cách 2: Qua Script

```bash
# Đặt ảnh vào thư mục known_faces/
# Format: Ten_1.jpg, Ten_2.jpg
python register_person.py
```

---

## Cấu hình hệ thống

Chỉnh sửa file `config.py`:

```python
# Camera
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# Nhận diện
FACE_RECOGNITION_TOLERANCE = 0.4

# Server
API_PORT = 5000
```

---

## Công cụ hỗ trợ

Kiểm tra camera:

```bash
python tools/check_camera.py
```

Xóa database:

```bash
python tools/force_clear_database.py
```

Reset database từ ảnh:

```bash
python tools/reset_db_from_known_faces.py
```

---

## Xử lý lỗi thường gặp

Không mở được camera:

* Kiểm tra bằng tool
* Thay đổi CAMERA_INDEX (0, 1, 2...)

Không nhận diện được khuôn mặt:

* Kiểm tra ảnh rõ nét
* Điều chỉnh FACE_RECOGNITION_TOLERANCE
* Nhấn phím l để reload

Lỗi "No valid faces detected":

* Ảnh không có khuôn mặt rõ
* Góc chụp không phù hợp

---

## Cấu trúc thư mục

```
ProjectTracking/
├── main.py
├── run_camera.py
├── register_person.py
├── config.py
├── app/
│   ├── api/routes.py
│   ├── models/
│   └── services/
├── templates/
├── known_faces/
├── tools/
└── database/
```

---

## API Endpoints

| Method | Endpoint               | Mô tả              |
| ------ | ---------------------- | ------------------ |
| GET    | /api/stats             | Thống kê real-time |
| GET    | /api/attendance        | Lịch sử chấm công  |
| GET    | /api/persons           | Danh sách người    |
| POST   | /api/persons/register  | Đăng ký người      |
| GET    | /api/export/attendance | Xuất dữ liệu       |

---

## Ghi chú

* Hệ thống sử dụng nhận diện khuôn mặt kết hợp tracking để tăng độ chính xác
* Có thể mở rộng:

  * Hỗ trợ nhiều camera
  * Kết nối database lớn (MySQL, PostgreSQL)
  * Triển khai lên cloud
