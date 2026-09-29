from tests.fd import between, esp_net, is_nc, parts_between, pulls


def test_module(nl):
    assert nl.components["U1"]["value"] == "ESP32-S3-WROOM-1-N16R8"
    assert nl.components["U1"]["fields"].get("LCSC") == "C2913202"
    assert nl.net_of_function("U1", "3V3") == "+3V3"
    assert all(nl.net_of("U1", p) == "GND" for p in (1, 40, 41))


def test_left_alone(nl):
    for gpio in (3, 12, 18, 35, 36, 37, 45, 46):
        assert is_nc(esp_net(nl, gpio)), gpio


def test_boot_and_reset(nl):
    assert esp_net(nl, 0) == "BOOT" and pulls(nl, "BOOT") == [("10K", "+3V3")]
    assert not parts_between(nl, "BOOT", "GND", "C")                       # no capacitor on GPIO0
    assert between(nl, "SW1") == {"BOOT", "GND"}
    en = nl.net_of_function("U1", "EN")
    assert pulls(nl, en) == [("10K", "+3V3")]
    assert [nl.components[c]["value"] for c in parts_between(nl, en, "GND", "C")] == ["1uF"]
    assert between(nl, "SW2") == {en, "GND"}


def test_usb(nl):
    assert esp_net(nl, 19) == "USB_DN" and esp_net(nl, 20) == "USB_DP"
    for esp_side, conn_side in (("USB_DP", "USB_DP_C"), ("USB_DN", "USB_DN_C")):
        refs = parts_between(nl, esp_side, conn_side)
        assert len(refs) == 1 and nl.components[refs[0]]["value"] == "22"
    assert nl.net_of("J3", "A6") == nl.net_of("J3", "B6") == "USB_DP_C"
    assert nl.net_of("J3", "A7") == nl.net_of("J3", "B7") == "USB_DN_C"
    for cc in ("A5", "B5"):
        net = nl.net_of("J3", cc)
        assert pulls(nl, net) == [("5K1", "GND")]
    assert nl.net_of("J3", "A5") != nl.net_of("J3", "B5")                  # two separate 5.1k
    assert {nl.net_of("U7", 1), nl.net_of("U7", 3)} == {"USB_DP_C", "USB_DN_C"}
    assert nl.net_of("U7", 5) == "VBUS" and nl.net_of("U7", 2) == "GND"


def test_led_uart_spare(nl):
    assert esp_net(nl, 2) == "LED"
    assert esp_net(nl, 43) == "ESP_TXD0" and esp_net(nl, 44) == "ESP_RXD0"
    tx = parts_between(nl, "ESP_TXD0", "UART_TX")
    assert len(tx) == 1 and nl.components[tx[0]]["value"] == "470"
    en = nl.net_of_function("U1", "EN")
    assert [nl.net_of("J4", p) for p in range(1, 7)] == ["UART_TX", "ESP_RXD0", en, "BOOT", "+3V3", "GND"]
    assert [nl.net_of("J5", p) for p in range(1, 7)] == ["GPIO13", "GPIO14", "GPIO47", "GPIO48", "+3V3", "GND"]
    for g in (13, 14, 47, 48):
        assert esp_net(nl, g) == f"GPIO{g}"
