#include <Arduino.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>

#define PIN_CLK PIN_PC0
#define PIN_MOSI PIN_PC2
#define PIN_CS PIN_PC3
#define PIN_DC PIN_PA3
#define PIN_RST PIN_PA4
#define PIN_BUTTON PIN_PA6

// External crystal / 8192 gives a 4 Hz RTC tick.
// PER = 79 means an overflow every 80 ticks = 20 seconds.
volatile uint32_t overflowWakeCount = 0;
volatile uint32_t observedOverflowWakeCount = 0;

#define DISABLE_PORT_INPUTS(port)      \
  do {                                 \
    port.PIN0CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN1CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN2CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN3CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN4CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN5CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN6CTRL = PORT_ISC_INPUT_DISABLE_gc; \
    port.PIN7CTRL = PORT_ISC_INPUT_DISABLE_gc; \
  } while (0)

ISR(RTC_CNT_vect) {
  if ((RTC.INTFLAGS & RTC_OVF_bm) != 0) {
    ++overflowWakeCount;
    RTC.INTFLAGS = RTC_OVF_bm;
  }
}

void setupDisplayPins() {
  pinMode(PIN_CLK, OUTPUT);
  digitalWrite(PIN_CLK, LOW);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_MOSI, LOW);
  pinMode(PIN_DC, OUTPUT);
  digitalWrite(PIN_DC, LOW);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, HIGH);
}

void writeDisplayByte(uint8_t value) {
  for (uint8_t mask = 0x80; mask != 0; mask >>= 1) {
    digitalWrite(PIN_MOSI, (value & mask) != 0 ? HIGH : LOW);
    digitalWrite(PIN_CLK, HIGH);
    digitalWrite(PIN_CLK, LOW);
  }
}

void sendDisplayCommand(uint8_t command) {
  digitalWrite(PIN_CS, LOW);
  digitalWrite(PIN_DC, LOW);
  writeDisplayByte(command);
  digitalWrite(PIN_CS, HIGH);
}

void shutdownDisplay() {
  setupDisplayPins();

  digitalWrite(PIN_RST, LOW);
  delay(20);
  digitalWrite(PIN_RST, HIGH);
  delay(10);

  sendDisplayCommand(0x28);  // DISPOFF
  sendDisplayCommand(0x10);  // SLPIN
  delay(5);

  digitalWrite(PIN_CLK, LOW);
  digitalWrite(PIN_MOSI, LOW);
  digitalWrite(PIN_DC, LOW);
  digitalWrite(PIN_CS, HIGH);
  digitalWrite(PIN_RST, HIGH);
}

void disableUnusedPeripherals() {
  ADC0.CTRLA = 0;

#ifdef AC0_CTRLA
  AC0.CTRLA = 0;
#endif
#ifdef DAC0_CTRLA
  DAC0.CTRLA = 0;
#endif
#ifdef VREF_CTRLA
  VREF.CTRLA = 0;
#endif
#ifdef CCL_CTRLA
  CCL.CTRLA = 0;
#endif
#ifdef USART0_CTRLA
  USART0.CTRLA = 0;
  USART0.CTRLB = 0;
#endif
#ifdef SPI0_CTRLA
  SPI0.CTRLA = 0;
  SPI0.INTCTRL = 0;
#endif
#ifdef TWI0_MCTRLA
  TWI0.MCTRLA = 0;
  TWI0.SCTRLA = 0;
#endif
#ifdef TCA0_SINGLE_CTRLA
  TCA0.SINGLE.CTRLA = 0;
  TCA0.SINGLE.INTCTRL = 0;
#endif
#ifdef TCB0_CTRLA
  TCB0.CTRLA = 0;
  TCB0.INTCTRL = 0;
#endif
#ifdef TCB1_CTRLA
  TCB1.CTRLA = 0;
  TCB1.INTCTRL = 0;
#endif

#ifdef BOD_SLEEP_DIS_gc
  BOD.CTRLA = (BOD.CTRLA & ~BOD_SLEEP_gm) | BOD_SLEEP_DIS_gc;
#endif
}

void disableDigitalInputBuffers() {
#ifdef PORTA
  DISABLE_PORT_INPUTS(PORTA);
#endif
#ifdef PORTB
  DISABLE_PORT_INPUTS(PORTB);
#endif
#ifdef PORTC
  DISABLE_PORT_INPUTS(PORTC);
#endif
}

void waitForRtcSync() {
  while (RTC.STATUS > 0 || RTC.PITSTATUS > 0) {
  }
}

void setupRTC() {
  waitForRtcSync();

  RTC.CTRLA = 0;
  RTC.INTCTRL = 0;
  RTC.INTFLAGS = RTC_OVF_bm | RTC_CMP_bm;
  RTC.PITINTCTRL = 0;
  RTC.PITCTRLA = 0;
  RTC.PITINTFLAGS = RTC_PI_bm;

  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_RUNSTDBY_bm | CLKCTRL_CSUT_64K_gc);
  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_ENABLE_bm | CLKCTRL_RUNSTDBY_bm |
                       CLKCTRL_CSUT_64K_gc);

  RTC.CLKSEL = RTC_CLKSEL_TOSC32K_gc;
  RTC.PER = 79;
  RTC.CNT = 0;

  waitForRtcSync();

  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV8192_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;

  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }
  while ((CLKCTRL.MCLKSTATUS & CLKCTRL_XOSC32KS_bm) == 0) {
  }
}

void enterStandby() {
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

void setup() {
  shutdownDisplay();
  setupRTC();
  disableUnusedPeripherals();
  disableDigitalInputBuffers();
  sei();
}

void loop() {
  enterStandby();
  observedOverflowWakeCount = overflowWakeCount;
}
