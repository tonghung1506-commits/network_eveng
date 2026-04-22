import os
import json
from openai import OpenAI
from netmiko import ConnectHandler
from dotenv import load_dotenv

# 1. Load biến môi trường
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
EVE_HOST = os.getenv("EVE_NG_HOST")

client = OpenAI(api_key=API_KEY)

# 2. Đọc cơ sở dữ liệu
try:
    with open("inventory.json", "r") as file:
        NETWORK_INVENTORY = json.load(file)
except Exception as e:
    print(f"❌ Lỗi đọc file inventory.json: {e}")
    exit()

def ai_orchestrator(user_input):
    """AI phân loại yêu cầu: ĐỌC, CẤU HÌNH, hay CHẶN (BẢO MẬT)"""
    device_names = ", ".join(NETWORK_INVENTORY.keys())
    prompt = f"""
    Bạn là Chuyên gia Bảo mật Mạng. Danh sách thiết bị: [{device_names}].
    Yêu cầu của sếp: "{user_input}"
    
    HÃY PHÂN TÍCH VÀ CHỌN 'action_type' THEO ĐÚNG THỨ TỰ ƯU TIÊN SAU:
    
    [ƯU TIÊN 1 - BẢO MẬT]: NẾU yêu cầu là tắt toàn bộ (shutdown), khởi động lại (reload, reboot) -> BẮT BUỘC trả về action_type là "block" và ghi rõ lý do cảnh báo. KHÔNG ĐƯỢC CẤP LỆNH.
    
    [ƯU TIÊN 2 - CẤU HÌNH]: NẾU yêu cầu là thay đổi cấu hình MỘT PHẦN (tắt/bật 1 cổng cụ thể, đổi IP) -> Trả về action_type là "config" và mảng lệnh. (VD: ["interface Ethernet0/0", "shutdown"]).
    
    [ƯU TIÊN 3 - ĐỌC THÔNG TIN]: NẾU yêu cầu chỉ là xem (show, ping) -> Trả về action_type là "show" và mảng lệnh.
    
    Trả về định dạng JSON:
    {{
        "target_device": "Tên thiết bị",
        "action_type": "block hoặc config hoặc show",
        "commands": ["lệnh 1", "lệnh 2"],
        "reason": "Lý do chặn (nếu có)"
    }}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        temperature=0, 
        messages=[{"role": "user", "content": prompt}]
    )
    # Tóm lấy kết quả JSON từ AI thay vì return luôn
    data = json.loads(response.choices[0].message.content)
    
    # 🛑 RÀO CHẮN THÉP BẰNG PYTHON (Đè quyền của AI)
    commands = data.get("commands", [])
    for cmd in commands:
        if any(bad_word in cmd.lower() for bad_word in ['reload', 'reboot', 'erase', 'write erase']):
            data["action_type"] = "block"
            data["reason"] = "Hệ thống an ninh Python tự động kích hoạt: Phát hiện lệnh nguy hiểm, đè quyền AI!"
            data["commands"] = [] # Xóa sạch lệnh để an toàn
            break # Dừng kiểm tra, chốt luôn là block
            
    # Trả kết quả đã được Python kiểm duyệt ra ngoài
    return data

def ai_analyze_output(commands, output):
    prompt = f"""
    Bạn là một Chuyên gia Phân tích Hệ thống Mạng Cisco. 
    Dưới đây là kết quả trả về từ thiết bị sau khi chạy mảng lệnh: {commands}
    
    [DỮ LIỆU TỪ THIẾT BỊ BẮT ĐẦU]
    {output}
    [DỮ LIỆU TỪ THIẾT BỊ KẾT THÚC]
    
    NHIỆM VỤ CỦA BẠN:
    Hãy đọc hiểu và tóm tắt các thông số mạng thực tế từ dữ liệu trên một cách ngắn gọn, chuyên nghiệp nhất.

    ⚠️ CÁC QUY TẮC KỶ LUẬT THÉP (BẮT BUỘC TUÂN THỦ):
    1. TRUNG THỰC TUYỆT ĐỐI: Chỉ báo cáo những gì có thật trong phần [DỮ LIỆU TỪ THIẾT BỊ]. Không tự suy diễn hay thêm thắt thông tin bên ngoài.
    2. CẤM ĐOÁN MÒ: TUYỆT ĐỐI KHÔNG phán đoán thiết bị đang ở chế độ nào (config mode, enable mode...). Đó không phải việc của bạn.
    3. CẤM TỰ VẢ: NẾU trong dữ liệu CÓ thông tin cấu hình (IP, trạng thái cổng...), TUYỆT ĐỐI KHÔNG ĐƯỢC thốt ra câu "không có kết quả trả về hiển thị". 
    4. XỬ LÝ LỖI: NẾU dữ liệu là các dòng báo lỗi (VD: % Incomplete command, % Invalid input), chỉ cần dịch lỗi đó ra tiếng Việt cho người dùng hiểu là đủ.
    5. ĐỊNH DẠNG: Trình bày bằng các gạch đầu dòng (-) ngắn gọn, súc tích. Không cần viết câu chào hỏi hay kết luận thừa thãi.
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def main():
    print("🛡️ HỆ THỐNG TRỢ LÝ MẠNG AI (TÍCH HỢP BẢO MẬT & AUTO-CONFIG) 🛡️\n")
    
    while True:
        user_intent = input("Sếp muốn yêu cầu gì? (nhập 'exit' để thoát): ")
        if user_intent.lower() == 'exit': break
        
        try:
            print("🤖 AI đang phân tích ý định...")
            ai_decision = ai_orchestrator(user_intent)
            device_name = ai_decision.get("target_device")
            action_type = ai_decision.get("action_type")
            commands = ai_decision.get("commands", [])
            reason = ai_decision.get("reason", "")
            
            # XỬ LÝ NHÓM LỆNH BỊ CẤM
            if action_type == "block":
                print(f"\n⛔ [CẢNH BÁO BẢO MẬT]: Yêu cầu bị khước từ!")
                print(f"Lý do: {reason}\n")
                continue

            if device_name not in NETWORK_INVENTORY:
                print(f"❌ Không tìm thấy thiết bị '{device_name}'.\n")
                continue
                
            print(f"\n💡 AI đề xuất -> Thiết bị: [{device_name}] | Loại: [{action_type.upper()}] | Lệnh: {commands}")
            
            confirm = input("⚠️ Chấp thuận thực thi? (Y/N): ")
            if confirm.strip().lower() == 'y':
                print(f"🚀 Đang thiết lập kết nối an toàn tới [{device_name}]...")
                
                # THÊM THAM SỐ 'secret' VÀO CẤU HÌNH KẾT NỐI
                device_config = {
                    'device_type': 'cisco_ios_telnet',
                    'host': EVE_HOST,
                    'port': NETWORK_INVENTORY[device_name]['port'],
                    'username': '',
                    'password': '',
                    'secret': '' # Mật khẩu enable (EVE-NG mặc định là rỗng)
                }
                
                net_connect = ConnectHandler(**device_config, global_delay_factor=2)
                
                # ÉP THIẾT BỊ LÊN QUYỀN CAO NHẤT (ENABLE MODE '#')
                try:
                    net_connect.enable()
                except Exception as e:
                    pass # Bỏ qua nếu thiết bị đã ở sẵn chế độ Enable
                
                output = ""
                
                
                # PHÂN LUỒNG THỰC THI DỰA VÀO ACTION_TYPE
                if action_type == "config":
                    # send_config_set tự động gõ 'configure terminal', nạp list lệnh, rồi gõ 'end'
                    output = net_connect.send_config_set(commands)
                else:
                    # Gửi từng lệnh show
                    for cmd in commands:
                        output += f"\n--- Kết quả: {cmd} ---\n"
                        output += net_connect.send_command(cmd)
                        
                net_connect.disconnect()
                
                print("\n" + "="*50)
                print("📋 DỮ LIỆU RAW TỪ THIẾT BỊ:")
                print(output if output.strip() else "[THỰC THI THÀNH CÔNG NHƯNG KHÔNG CÓ DATA HIỂN THỊ]")
                print("="*50)
                
                if output.strip():
                    print("\n📊 AI ĐANG PHÂN TÍCH BÁO CÁO...")
                    print("-" * 50)
                    print(ai_analyze_output(commands, output))
                    print("-" * 50 + "\n")
            else:
                print("🛑 Đã hủy thao tác.\n")
                
        except Exception as e:
            print(f"❌ Lỗi hệ thống: {e}\n")

if __name__ == "__main__":
    main()