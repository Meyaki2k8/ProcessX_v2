<p align="center">
  <img src="assets/Meyaki.ico" alt="ProcessX Logo" width="80" height="80">
</p>

<h1 align="center">ProcessX v2.0</h1>

<p align="center">
  <b>Advanced Windows Process & CPU Optimization Utility</b><br>
  <i>Công cụ tối ưu hóa tiến trình & hiệu năng CPU chuyên sâu cho Windows</i>
</p>

<p align="center">
  <a href="#english">English</a> • <a href="#tiếng-việt">Tiếng Việt</a>
</p>

---

<a name="english"></a>

## 🇬🇧 English

### 📌 Overview

**ProcessX v2** is a complete, from-scratch remake covering both the core engine and user interface

While inspired by the initial concepts of [ProcessX](https://github.com/jadenpeek/ProcessX) and the automated affinity balancing ideas of [Bitsum Process Lasso](https://bitsum.com/), this version is entirely rewritten and developed independently. This standalone architecture allows rapid feature additions, advanced tuning capabilities, and direct updates without waiting for upstream pull request reviews

---

### ✨ Key Features

1. **Intelligent Process Tree & Live Monitoring:**
   - Real-time CPU, RAM, and process hierarchy tree view with ancestor guide lines
   - Dynamic 3-step executable icon and path resolution (Win32 API `QueryFullProcessImageNameW`, psutil, and dynamic Windows directory lookup) with zero hardcoding
   - Automatic child process grouping and Windows service tagging

2. **CPU Sets & Affinity Automation:**
   - Native Windows CPU Sets integration to bind processes to specific logical or physical cores
   - Presets for All Cores, Physical Cores Only (bypassing SMT/Hyper-Threading for reduced gaming frame-time variance), or Custom Core Masks

3. **Multi-level Priority & Resource Control:**
   - Windows CPU Scheduling Priority (Idle, Below Normal, Normal, Above Normal, High, Realtime)
   - I/O Priority tuning (Very Low, Low, Normal, High) via undocumented NT kernel APIs
   - Memory Priority (Very Low, Low, Medium, Below Normal, Normal)

4. **Dynamic Power Plan Switching:**
   - Automatically switches Windows Power Schemes when target games or high-load processes launch, and restores the previous power plan when they exit

5. **Modern Obsidian Glassmorphism UI:**
   - Custom frameless dark theme featuring deep obsidian surfaces, vector controls, and Windows DWM Mica/Acrylic blur effects
   - High-DPI support, smooth scrolling, and full bilingual interface (English and Vietnamese)

6. **System Integration & Lightweight Packaging:**
   - Native Windows Task Scheduler integration for elevated startup without UAC prompts
   - Minimize-to-tray background daemon watcher with adaptive polling intervals
   - Rules configuration export and import via clean JSON profiles

---

### 📂 Project Structure

```text
ProcessX_v2/
├── assets/
│   └── Meyaki.ico              # Application branding icon
├── installer/
│   ├── build.bat               # Automated PyInstaller & NSIS build script
│   ├── ProcessX.nsi            # NSIS installer packaging script
│   └── version_info.txt        # Windows PE executable version metadata
├── .gitignore                  # Git ignore definitions
├── config.py                   # Settings, localization dictionaries (VI/EN), and rule schemas
├── core.py                     # Native Win32 / NT APIs, CPU Sets topology, and watcher thread
├── main.py                     # Application entry point with single-instance mutex
├── ui.py                       # Modern PyQt6 frameless obsidian interface
├── LICENSE                     # MIT License (EN & VN)
└── README.md                   # Project documentation
```

---

### 🛠️ System Requirements & Setup

#### Requirements:

- **Operating System:** Windows 10 / Windows 11 (64-bit)
- **Python:** 3.10+ (if running from source)
- **Permissions:** Administrator privileges (required to adjust priority and CPU sets for protected processes)

#### Development Environment:

1. Clone the repository:

   ```bash
   git clone [https://github.com/](https://github.com/)[your-username]/ProcessX_v2.git
   cd ProcessX_v2
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install required dependencies:

   ```bash
   pip install psutil PyQt6 pyinstaller
   ```

4. Launch the application:
   ```bash
   python main.py
   ```

---

### 📦 Building the Installer

The project includes an automated script that compiles the Python source using PyInstaller and packages it with NSIS:

1. Install [NSIS (Nullsoft Scriptable Install System)](https://nsis.sourceforge.io/) and ensure `makensis.exe` is added to your system `PATH`
2. Navigate to the `installer` directory and execute:
   ```cmd
   cd installer
   build.bat
   ```
3. The standalone installer executable will be generated inside the `dist` folder

---

### 📜 Credits & Disclaimer

- **Inspirations:**
  - [ProcessX](https://github.com/jadenpeek/ProcessX) by `jadenpeek`
  - [Process Lasso](https://bitsum.com/) by Bitsum LLC
- **Disclaimer:**
  - ProcessX v2 is an independent open-source project and is neither affiliated with nor endorsed by Bitsum LLC or the original ProcessX creator
  - Modifying critical operating system processes or affinities incorrectly may lead to system instability. Use with appropriate care

---

<br>

---

<a name="tiếng-việt"></a>

## 🇻🇳 Tiếng Việt

### 📌 Giới thiệu

**ProcessX v2** là phiên bản được viết lại toàn bộ từ đầu (full rewrite) cả về giao diện lẫn mã nguồn lõi xử lý

Dự án kế thừa ý tưởng quản lý tiến trình của [ProcessX](https://github.com/jadenpeek/ProcessX) và cơ chế tự động gán CPU, cân bằng luồng của [Process Lasso](https://bitsum.com/). Phiên bản v2 hoàn toàn độc lập với dự án gốc, giúp chủ động bổ sung các tính năng chuyên sâu cho Windows, tối ưu độ trễ game và cập nhật nhanh chóng mà không phụ thuộc vào việc duyệt tính năng từ tác giả bản gốc

---

### ✨ Tính năng chính

1. **Cây tiến trình trực quan & Giám sát thời gian thực:**
   - Hiển thị cấu trúc cha con dạng cây kèm đường dẫn nhánh Process Lasso rõ ràng, giám sát CPU, RAM và trạng thái theo chu kỳ mượt mà
   - Nhận diện đường dẫn file thực thi và trích xuất icon tự động 3 bước (Win32 API `QueryFullProcessImageNameW`, psutil và dò tìm trong thư mục hệ thống), không hardcode đường dẫn
   - Tự động gộp tiến trình con và hiển thị tên dịch vụ Windows Service đi kèm

2. **Quản lý CPU Sets & CPU Affinity tự động:**
   - Tận dụng cơ chế CPU Sets của Windows để cố định ứng dụng vào các luồng xử lý mong muốn
   - Hỗ trợ các cấu hình nhanh: Tất cả CPU, Chỉ Cores thực (loại bỏ luồng ảo SMT/Hyper-Threading để ổn định frame-time khi chơi game), hoặc chọn từng nhân tùy ý

3. **Điều khiển ưu tiên tài nguyên đa tầng:**
   - Độ ưu tiên CPU (Nghỉ, Dưới Bình Thường, Bình Thường, Trên Bình Thường, Cao, Thời Gian Thực)
   - Độ ưu tiên I/O đọc ghi đĩa (Rất thấp, Thấp, Bình Thường, Cao) qua các API NT kernel
   - Độ ưu tiên bộ nhớ (Rất thấp, Thấp, Trung Bình, Dưới Bình Thường, Bình Thường)

4. **Tự động chuyển đổi gói điện năng (Power Plan):**
   - Tự động kích hoạt gói hiệu năng cao khi mở game hoặc ứng dụng nặng, và tự động khôi phục lại gói nguồn ban đầu khi ứng dụng đóng

5. **Giao diện Obsidian Glassmorphism hiện đại:**
   - Thiết kế Dark Theme tông đen obsidian, bo góc sắc nét, điều khiển dạng vector cùng hiệu ứng mờ DWM Mica/Acrylic của Windows
   - Tương thích tốt với màn hình High-DPI, cuộn mượt và hỗ trợ chuyển đổi song ngữ Anh - Việt trực tiếp trên thanh tiêu đề

6. **Tích hợp sâu vào Windows:**
   - Đăng ký khởi động cùng Windows qua Task Scheduler, tự động cấp quyền Admin mà không bị thông báo UAC làm phiền
   - Chạy ẩn dưới khay hệ thống (System Tray) với cơ chế nền tự động phát hiện ứng dụng mới mở
   - Hỗ trợ xuất và nhập danh sách cấu hình rules thông qua file JSON

---

### 📂 Cấu trúc thư mục

```text
ProcessX_v2/
├── assets/
│   └── Meyaki.ico              # Icon ứng dụng
├── installer/
│   ├── build.bat               # Script tự động build file thực thi và bộ cài đặt
│   ├── ProcessX.nsi            # Script cấu hình NSIS installer
│   └── version_info.txt        # Thông tin phiên bản file PE (.exe)
├── .gitignore                  # Cấu hình bỏ qua tệp rác khi dùng Git
├── config.py                   # Lưu trữ cấu hình, bộ từ khóa song ngữ VI/EN, định dạng rules
├── core.py                     # API Win32 / NT, topo CPU Sets, quản lý nguồn và luồng nền
├── main.py                     # Entry point khởi động ứng dụng với Single Instance Mutex
├── ui.py                       # Giao diện PyQt6 frameless obsidian hiện đại
├── LICENSE                     # Giấy phép MIT (Bản tiếng Anh & Bản dịch tiếng Việt)
└── README.md                   # Tài liệu hướng dẫn dự án
```

---

### 🛠️ Yêu cầu hệ thống & Hướng dẫn cài đặt

#### Yêu cầu:

- **Hệ điều hành:** Windows 10 / Windows 11 (64-bit)
- **Python:** 3.10 trở lên (nếu chạy từ mã nguồn)
- **Quyền hạn:** Chạy dưới quyền Administrator để có thể can thiệp độ ưu tiên và CPU Sets của các tiến trình hệ thống

#### Chạy từ mã nguồn:

1. Tải mã nguồn về máy:

   ```bash
   git clone [https://github.com/](https://github.com/)[your-username]/ProcessX_v2.git
   cd ProcessX_v2
   ```

2. Tạo và kích hoạt môi trường ảo:

   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. Cài đặt các thư viện phụ thuộc:

   ```bash
   pip install psutil PyQt6 pyinstaller
   ```

4. Khởi chạy ứng dụng:
   ```bash
   python main.py
   ```

---

### 📦 Đóng gói ứng dụng thành Installer

Dự án đã chuẩn bị sẵn kịch bản biên dịch thành file `.exe` bằng PyInstaller và đóng gói file cài đặt NSIS:

1. Cài đặt [NSIS](https://nsis.sourceforge.io/) và kiểm tra biến môi trường `PATH` đã nhận lệnh `makensis.exe`
2. Mở cửa sổ dòng lệnh tại thư mục `installer` và chạy:
   ```cmd
   cd installer
   build.bat
   ```
3. File cài đặt hoàn chỉnh sẽ nằm trong thư mục `dist`

---

### 📜 Ghi công & Tuyên bố miễn trừ

- **Cảm hứng dự án:**
  - Dự án [ProcessX](https://github.com/jadenpeek/ProcessX) của tác giả `jadenpeek`
  - Cơ chế điều phối của [Process Lasso](https://bitsum.com/) từ Bitsum LLC
- **Tuyên bố miễn trừ:**
  - ProcessX v2 là phần mềm độc lập, không thuộc quyền sở hữu hay quản lý của Bitsum LLC cũng như tác giả ProcessX gốc
  - Việc can thiệp vào các tiến trình nhạy cảm của Windows có thể dẫn đến hiện tượng treo hoặc khởi động lại máy nếu cấu hình không phù hợp, người dùng cần lưu ý khi thiết lập quy tắc cho tiến trình hệ thống

---

## 📄 License

Project is distributed under the **[MIT License](LICENSE)** (Dự án được phân phối theo giấy phép MIT)
