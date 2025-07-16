#!/bin/bash
set -e

# --- 變數設定 (請確保與 bleConfig.json 一致) ---
if [ -n "$SUDO_USER" ]; then
    RUN_USER=$SUDO_USER
else
    RUN_USER=$(logname)
fi
echo "將使用用戶 '${RUN_USER}' 來運行服務。"

PROJECT_NAME="ble_data_service"
PROJECT_DIR="/home/${RUN_USER}/${PROJECT_NAME}"
VENV_DIR="${PROJECT_DIR}/venv"
SERVICE_NAME="ble_data_service"
WEB_PORT=5000  # 對應 bleConfig.json 中的 web_server.port
MQTT_PORT=1883 # 對應 bleConfig.json 中的 mqtt.port
SSH_PORT=22

# --- 0. 檢查必要檔案 ---
echo "[0/6] 正在檢查必要檔案..."
if [ ! -f "BLEmqttDatabase.py" ] || [ ! -f "bleConfig.json" ]; then
    echo "錯誤：找不到 BLEmqttDatabase.py 或 bleConfig.json 檔案！"
    echo "請將這兩個檔案與此腳本放在同一個目錄下再執行。"
    exit 1
fi
echo "檔案檢查通過。"


echo "--- 開始部署 ${PROJECT_NAME} ---"
echo "專案目錄: ${PROJECT_DIR}"
echo "Web 服務端口: ${WEB_PORT}"

# --- 1. 建立專案目錄並移動檔案 ---
# echo "[1/6] 正在建立專案目錄並移動檔案..."
# mkdir -p "${PROJECT_DIR}"
# mv ./BLEmqttDatabase.py "${PROJECT_DIR}/"
# mv ./bleConfig.json "${PROJECT_DIR}/"
# echo "檔案移動完成。"

# --- 2. 設定目錄權限 ---
echo "[2/6] 正在設定目錄權限..."
chown -R ${RUN_USER}:${RUN_USER} "${PROJECT_DIR}"
echo "權限已設定為用戶 ${RUN_USER}。"

# --- 3. 建立並啟用 Python 虛擬環境 ---
echo "[3/6] 正在設定 Python 虛擬環境..."
# 以 RUN_USER 的身份建立虛擬環境，避免權限問題
sudo -u ${RUN_USER} python3 -m venv "${VENV_DIR}"
echo "虛擬環境已建立。"

echo "正在虛擬環境中安裝必要的 Python 套件..."
# 直接使用虛擬環境中的 pip 來安裝
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install paho-mqtt pandas numpy matplotlib flask
echo "Python 套件安裝完成。"

# --- 4. 設定 UFW 防火牆 ---
echo "[4/6] 正在設定防火牆 (UFW)..."
ufw allow ${SSH_PORT}/tcp comment 'Allow SSH'
ufw allow ${MQTT_PORT}/tcp comment 'Allow MQTT'
ufw allow ${WEB_PORT}/tcp comment 'Allow BLE Web App'
yes | ufw enable # 強制啟用防火牆
ufw status verbose
echo "防火牆設定完成。"

# --- 5. 建立 systemd 服務 ---
echo "[5/6] 正在建立 systemd 服務..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# 採用您腳本中更穩健的寫法
cat << EOF | sudo tee ${SERVICE_FILE}
[Unit]
Description=BLE Data MQTT Processor Service
After=network.target

[Service]
User=${RUN_USER}
Group=$(id -gn ${RUN_USER})
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=python3 BLEmqttDatabase.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "服務設定檔已建立於 ${SERVICE_FILE}"

# --- 6. 啟用並啟動服務 ---
echo "[6/6] 正在啟用並啟動服務..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME} 
echo "服務已啟動。"

echo "--- 部署完成！ ---"
echo "您現在可以使用以下指令來檢查服務狀態："
echo "sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "若要查看即時日誌，請使用："
echo "sudo journalctl -u ${SERVICE_NAME} -f"