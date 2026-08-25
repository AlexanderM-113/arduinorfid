#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>

#define SS_PIN 10
#define RST_PIN 9
#define BTN_START 2  // Press to start cloning
#define BTN_CONFIRM 3 // Confirm action
#define STATUS_LED 7

MFRC522 mfrc522(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;
LiquidCrystal_I2C lcd(0x27, 16, 2);

int clone_state = 0;  // 0=idle, 1=reading, 2=writing
String source_uid = "";
String target_uid = "";
byte source_data[48];  // Store sectors 1-3 (3×16 bytes)
int source_data_size = 0;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();
  
  pinMode(BTN_START, INPUT_PULLUP);
  pinMode(BTN_CONFIRM, INPUT_PULLUP);
  pinMode(STATUS_LED, OUTPUT);
  
  Wire.begin();
  lcd.init();
  lcd.backlight();
  
  // Default key for MIFARE Classic
  for (byte i = 0; i < 6; i++) {
    key.keyByte[i] = 0xFF;
  }
  
  lcd.setCursor(0, 0);
  lcd.print("RFID Card Cloner");
  lcd.setCursor(0, 1);
  lcd.print("Press START btn");
  delay(2000);
  lcd.clear();
  
  Serial.println("[CLONER] Ready");
}

void loop() {
  // STATE 0: IDLE - Wait for start button
  if (clone_state == 0) {
    lcd.setCursor(0, 0);
    lcd.print("Ready to Clone");
    lcd.setCursor(0, 1);
    lcd.print("Press START");
    
    if (digitalRead(BTN_START) == LOW) {
      delay(300);
      clone_state = 1;
      lcd.clear();
      Serial.println("[CLONER] Starting...");
    }
    return;
  }

  // STATE 1: READ SOURCE CARD
  if (clone_state == 1) {
    lcd.setCursor(0, 0);
    lcd.print("Scan SOURCE");
    lcd.setCursor(0, 1);
    lcd.print("card to clone");

    if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
      return;
    }

    source_uid = getUID();
    Serial.println("[CLONER] Source UID: " + source_uid);

    if (readSectors(source_data, source_data_size)) {
      Serial.println("[CLONER] ✅ Read OK");
      
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Read Success!");
      lcd.setCursor(0, 1);
      lcd.print("UID: " + source_uid.substring(0, 8));
      
      delay(2000);
      lcd.clear();
      clone_state = 2;
    } else {
      Serial.println("[CLONER] ❌ Read Failed");
      lcd.clear();
      lcd.print("Read FAILED!");
      delay(2000);
      clone_state = 0;
    }

    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
  }

  // STATE 2: WRITE TO TARGET CARD
  if (clone_state == 2) {
    lcd.setCursor(0, 0);
    lcd.print("Scan TARGET");
    lcd.setCursor(0, 1);
    lcd.print("card to write");

    if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
      return;
    }

    target_uid = getUID();
    Serial.println("[CLONER] Target UID: " + target_uid);

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Confirm clone?");
    lcd.setCursor(0, 1);
    lcd.print("Press BTN2");
    
    delay(500);

    unsigned long timeout = millis();
    while (millis() - timeout < 10000) {
      if (digitalRead(BTN_CONFIRM) == LOW) {
        delay(300);
        
        lcd.clear();
        lcd.print("Writing...");
        
        if (writeSectors(source_data, source_data_size)) {
          Serial.println("[CLONER] ✅ Clone SUCCESS");
          Serial.println("[CLONE_OP] " + source_uid + " -> " + target_uid);
          
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print("Clone SUCCESS!");
          lcd.setCursor(0, 1);
          lcd.print("New card ready");
          
          // Flash LED
          for(int i = 0; i < 3; i++) {
            digitalWrite(STATUS_LED, HIGH);
            delay(200);
            digitalWrite(STATUS_LED, LOW);
            delay(200);
          }
          
          delay(2000);
          clone_state = 0;
        } else {
          Serial.println("[CLONER] ❌ Write Failed");
          lcd.clear();
          lcd.print("Write FAILED!");
          delay(2000);
          clone_state = 0;
        }
        break;
      }
    }

    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
  }
}

String getUID() {
  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    byte b = mfrc522.uid.uidByte[i];
    if (b < 0x10) uid += "0";
    uid += String(b, HEX);
  }
  return uid;
}

bool readSectors(byte* buffer, int &size) {
  size = 0;
  
  // Read sectors 1-3 (skip sector 0 which contains UID)
  for (byte sector = 1; sector <= 3; sector++) {
    for (byte block = 0; block < 4; block++) {
      byte blockAddr = sector * 4 + block;
      
      MFRC522::StatusCode status = mfrc522.PCD_Authenticate(
        MFRC522::PICC_CMD_MF_AUTH_KEY_A,
        blockAddr,
        &key,
        &(mfrc522.uid)
      );

      if (status != MFRC522::STATUS_OK) return false;

      byte buffer_size = 18;
      byte read_buffer[18];
      
      status = mfrc522.MIFARE_Read(blockAddr, read_buffer, &buffer_size);
      if (status != MFRC522::STATUS_OK) return false;

      for (byte i = 0; i < 16; i++) {
        buffer[size++] = read_buffer[i];
      }
    }
  }
  return true;
}

bool writeSectors(byte* buffer, int size) {
  int buf_idx = 0;
  
  for (byte sector = 1; sector <= 3; sector++) {
    for (byte block = 0; block < 4; block++) {
      byte blockAddr = sector * 4 + block;
      
      MFRC522::StatusCode status = mfrc522.PCD_Authenticate(
        MFRC522::PICC_CMD_MF_AUTH_KEY_A,
        blockAddr,
        &key,
        &(mfrc522.uid)
      );

      if (status != MFRC522::STATUS_OK) return false;

      byte write_buffer[16];
      for (byte i = 0; i < 16; i++) {
        write_buffer[i] = (buf_idx < size) ? buffer[buf_idx++] : 0x00;
      }

      status = mfrc522.MIFARE_Write(blockAddr, write_buffer, 16);
      if (status != MFRC522::STATUS_OK) return false;
    }
  }
  return true;
}
