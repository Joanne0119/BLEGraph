#!/bin/bash
set -e

# --- 變數設定 (請根據您的情況修改) ---
# 域名，Certbot 與 Nginx 將會使用此域名
DOMAIN="dces.app"
# 用於申請 Let's Encrypt 憑證的 Email，用於接收續約通知
ADMIN_EMAIL="joanneliu0119@gmail.com"

# --- 自動偵測執行用戶 ---
if [ -n "$SUDO_USER" ]; then
    RUN_USER=$SUDO_USER
else
    RUN_USER=$(logname)
fi
echo "將使用用戶 '${RUN_USER}' 來運行服務。"

# --- 專案與服務設定 (請確保與 bleConfig.json 一致) ---
PROJECT_NAME="ble_data_service"
PROJECT_DIR="/home/${RUN_USER}/${PROJECT_NAME}"
VENV_DIR="${PROJECT_DIR}/venv"
SERVICE_NAME="ble_data_service"
WEB_PORT=5000  # Python Flask 應用程式監聽的內部端口
MQTT_PORT=1883 # MQTT 服務器端口
SSH_PORT=22    # SSH 端口

# --- 0. 檢查與準備 ---
echo "[0/7] 正在檢查必要檔案..."
if [ ! -f "BLEmqttDatabase.py" ] || [ ! -f "bleConfig.json" ]; then
    echo "錯誤：找不到 BLEmqttDatabase.py 或 bleConfig.json 檔案！"
    echo "請將這兩個檔案與此腳本放在同一個目錄下再執行。"
    exit 1
fi
if [ "$ADMIN_EMAIL" == "your-email@example.com" ]; then
    echo "警告：請修改腳本中的 ADMIN_EMAIL 變數！"
    exit 1
fi
echo "檔案檢查通過。"

echo "--- 開始部署 ${PROJECT_NAME} ---"

# --- 1. 安裝必要的系統套件 ---
echo "[1/7] 正在更新系統並安裝 Nginx, Certbot, Python..."
sudo apt-get update
sudo apt-get install -y nginx python3-certbot-nginx python3-pip python3-venv ufw sqlite3 net-tools

# --- 2. 建立專案目錄並移動檔案 ---
# echo "[2/7] 正在建立專案目錄並移動檔案..."
# mkdir -p "${PROJECT_DIR}"
# # 使用 cp 而非 mv，保留原始檔案
# cp ./BLEmqttDatabase.py "${PROJECT_DIR}/"
# cp ./bleConfig.json "${PROJECT_DIR}/"
# echo "檔案複製完成。"

# --- 3. 設定目錄權限與 Python 虛擬環境 ---
echo "[3/7] 正在設定權限與 Python 虛擬環境..."
sudo chown -R ${RUN_USER}:${RUN_USER} "${PROJECT_DIR}"
sudo -u ${RUN_USER} python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install paho-mqtt pandas numpy matplotlib flask
echo "Python 環境設定完成。"

# --- 4. 設定 UFW 防火牆 ---
echo "[4/7] 正在設定防火牆 (UFW)..."
sudo ufw allow ${SSH_PORT}/tcp comment 'Allow SSH'
sudo ufw allow ${MQTT_PORT}/tcp comment 'Allow MQTT'
# 允許 Nginx 的流量 (HTTP & HTTPS)，不再需要直接開放 5000 port 到公網
sudo ufw allow 'Nginx Full'
yes | sudo ufw enable
sudo ufw status verbose
echo "防火牆設定完成。"

# --- 5. 設定 Nginx 反向代理與 SSL ---
echo "[5/7] 正在設定 Nginx 反向代理..."

# 建立 Nginx 設定檔，將流量轉發到本地的 Flask 應用
sudo tee /etc/nginx/sites-available/${DOMAIN} > /dev/null <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 啟用網站設定
sudo ln -s -f /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/

# 檢查 Nginx 語法並重新載入
sudo nginx -t
sudo systemctl reload nginx

echo "正在為 ${DOMAIN} 申請 SSL 憑證並自動設定 Nginx..."
# 使用 --non-interactive 參數讓腳本自動執行
sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos -m ${ADMIN_EMAIL}

echo "Nginx 與 SSL 設定完成。"

# --- 6. 建立 systemd 服務 ---
echo "[6/7] 正在建立 systemd 服務..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee ${SERVICE_FILE} > /dev/null <<EOF
[Unit]
Description=BLE Data MQTT Processor Service
After=network.target

[Service]
User=${RUN_USER}
Group=$(id -gn ${RUN_USER})
WorkingDirectory=${PROJECT_DIR}
ExecStart=${VENV_DIR}/bin/python3 main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
echo "服務設定檔已建立於 ${SERVICE_FILE}"

# --- 7. 啟用並啟動服務 ---
echo "[7/7] 正在啟用並啟動服務..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
echo "服務已啟動。"

echo "--- 部署完成！ ---"
echo "您的服務現在可以透過 https://${DOMAIN} 存取。"
echo "您可以使用以下指令來檢查服務狀態："
echo "sudo systemctl status ${SERVICE_NAME}"
echo "若要查看即時日誌，請使用："
echo "sudo journalctl -u ${SERVICE_NAME} -f"