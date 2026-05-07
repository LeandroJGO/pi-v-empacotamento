const int PINO_CHAVE = 4;

bool ultimoEstado = HIGH;
unsigned long ultimoDebounce = 0;
const unsigned long debounceDelay = 80;

void setup() {
  pinMode(PINO_CHAVE, INPUT_PULLUP);
  Serial.begin(115200);
  delay(500);

  ultimoEstado = digitalRead(PINO_CHAVE);

  Serial.println("SISTEMA_PRONTO");
}

void loop() {
  bool leitura = digitalRead(PINO_CHAVE);

  if (leitura != ultimoEstado) {
    ultimoDebounce = millis();
  }

  if ((millis() - ultimoDebounce) > debounceDelay) {
    static bool estadoConfirmado = HIGH;

    if (leitura != estadoConfirmado) {
      estadoConfirmado = leitura;

      if (estadoConfirmado == LOW) {
        Serial.println("START");
      } else {
        Serial.println("STOP");
      }
    }
  }

  ultimoEstado = leitura;
}