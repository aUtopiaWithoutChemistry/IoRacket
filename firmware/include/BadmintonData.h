/**
 * This is the header file defining the Badminton Data structure.
 * 
 * @author Zifan Zuo
 * @date 2026-Jan-26
 */

#pragma once

#include <cstdint>

/**
 * Badminton data structure for BLE transmission.
 * 4 bytes timestamp + 6 floats (4 bytes each) = 28 bytes total
 */
struct __attribute__((packed)) BadmintonData {
  uint32_t timestamp;
  float acc[3];
  float gyro[3];
};