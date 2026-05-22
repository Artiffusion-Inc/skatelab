package ru.skatelab.capture.data.ble

/**
 * Builds WT901 BLE command packets and sequences.
 *
 * All commands are 5 bytes: [0xFF, 0xAA, b3, b4, b5].
 * Byte 3 = register address for writes, 0x27 for register reads.
 *
 * Unlock must be sent before EVERY configuration write — the 10-second
 * window expires after Save. Register reads do NOT need Unlock.
 *
 * BLE connect sends ONLY setRate() — no unlock/save/accCalibrate.
 * See: docs/specs/2026-05-14-ble-stack-redesign-design.md
 */
object Wt901Commander {
    // Register addresses
    private const val REG_OUTPUT_RATE: Byte = 0x03
    private const val REG_READ_OPCODE: Byte = 0x27

    // Calibration commands (WitMotion WT901 protocol)
    private const val CMD_ACC_CALIB: Byte = 0x01

    // Command prefix
    private const val CMD_PREFIX_0: Byte = 0xFF.toByte()
    private const val CMD_PREFIX_1: Byte = 0xAA.toByte()

    // Inter-command delays (from XAMLCORP C# SDK + spec)
    private const val DELAY_AFTER_UNLOCK_MS = 50L
    private const val DELAY_BETWEEN_CONFIG_MS = 100L
    private const val DELAY_AFTER_SAVE_MS = 500L
    private const val DELAY_ACC_CALIB_MS = 2000L

    /** A single command step with bytes to send and a delay after sending. */
    data class CommandStep(
        val bytes: ByteArray,
        val delayAfterMs: Long,
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (other !is CommandStep) return false
            return bytes.contentEquals(other.bytes) && delayAfterMs == other.delayAfterMs
        }

        override fun hashCode(): Int {
            var result = bytes.contentHashCode()
            result = 31 * result + delayAfterMs.hashCode()
            return result
        }
    }

    // --- Atomic commands ---

    /** Unlock the sensor for configuration (opens 10-second window). */
    fun unlock(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x69, 0x88.toByte(), 0xB5.toByte())

    /** Start accelerometer hardware calibration — sensor must be still and level. */
    fun accCalibrate(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, CMD_ACC_CALIB, 0x01, 0x00)

    /** Stop active calibration (ACC or MAG). */
    fun stopCalibration(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, CMD_ACC_CALIB, 0x00, 0x00)

    /**
     * Set OutputRate register (0x03).
     * @param value Rate code. 0x09 = 100Hz.
     * This is the ONLY command sent on BLE connect.
     */
    fun setRate(value: Int): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, REG_OUTPUT_RATE, value.toByte(), 0x00)

    /** Set sensor date — year/month register (0x30). */
    fun setTimeYearMonth(
        year: Int,
        month: Int,
    ): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x30, month.toByte(), (year - 2000).toByte())

    /** Set sensor date — hour/day register (0x31). */
    fun setTimeHourDay(
        hour: Int,
        day: Int,
    ): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x31, hour.toByte(), day.toByte())

    /** Set sensor time — second/minute register (0x32). */
    fun setTimeSecondMinute(
        second: Int,
        minute: Int,
    ): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x32, second.toByte(), minute.toByte())

    /**
     * Time configuration sequence: writes current Android time to sensor.
     * Must be called BEFORE streaming starts (WT901 ignores register writes during streaming).
     * Sequence: unlock → setTimeYearMonth → setTimeHourDay → setTimeSecondMinute → save
     */
    fun timeConfigSequence(): List<CommandStep> {
        val now = java.util.Calendar.getInstance()
        return listOf(
            CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
            CommandStep(
                setTimeYearMonth(now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH) + 1),
                DELAY_BETWEEN_CONFIG_MS,
            ),
            CommandStep(
                setTimeHourDay(now.get(java.util.Calendar.HOUR_OF_DAY), now.get(java.util.Calendar.DAY_OF_MONTH)),
                DELAY_BETWEEN_CONFIG_MS,
            ),
            CommandStep(
                setTimeSecondMinute(now.get(java.util.Calendar.SECOND), now.get(java.util.Calendar.MINUTE)),
                DELAY_BETWEEN_CONFIG_MS,
            ),
            CommandStep(save(), DELAY_AFTER_SAVE_MS),
        )
    }

    /** Restart sensor — reboots without changing stored config. Drops GATT connection. */
    fun restart(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x00, 0xFF.toByte(), 0x00)

    /** Factory reset — restores all registers to defaults and reboots. Drops GATT connection. */
    fun factoryReset(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x00, 0x01, 0x00)

    /** Save configuration to flash (no reboot). Must send after any config write. */
    fun save(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x00, 0x00, 0x00)

    /**
     * Read a register value (query-response via 0x71 notification).
     * Register reads do NOT need Unlock.
     */
    fun readRegister(reg: Int): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, REG_READ_OPCODE, reg.toByte(), 0x00)

    /** Undocumented wake-up sequence (FF F0 F0 F0 F0). Some firmware needs this before unlock. */
    fun wakeUp(): ByteArray = byteArrayOf(0xFF.toByte(), 0xF0.toByte(), 0xF0.toByte(), 0xF0.toByte(), 0xF0.toByte())

    // --- Recovery sequences (manual only, NOT on connect) ---

    /**
     * ACC calibration recovery sequence for BLE.
     * Use when ACC data in 0x61 frame is all zeros (corrupted offset).
     * Sensor MUST be horizontal and completely still during calibration.
     *
     * Sequence: stopCalib → unlock → stopCalib(working mode) → unlock → accCalibrate → save
     * Two stopCalib calls ensure sensor is in working mode before calibration.
     * Two unlock calls guard against expired unlock window.
     */
    fun bleAccCalibrateSequence(): List<CommandStep> =
        listOf(
            CommandStep(stopCalibration(), DELAY_BETWEEN_CONFIG_MS),
            CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
            // working mode first (critical!)
            CommandStep(stopCalibration(), DELAY_ACC_CALIB_MS),
            CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
            // start ACC cal — sensor must be STILL
            CommandStep(accCalibrate(), DELAY_ACC_CALIB_MS),
            CommandStep(save(), DELAY_AFTER_SAVE_MS),
        )

    /**
     * ACC calibration with wake-up — for stubborn firmware versions.
     * Sensor MUST be horizontal and completely still.
     */
    fun bleAccCalibrateWithWakeSequence(): List<CommandStep> =
        listOf(
            CommandStep(wakeUp(), DELAY_BETWEEN_CONFIG_MS),
            CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
            CommandStep(stopCalibration(), DELAY_ACC_CALIB_MS),
            CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
            CommandStep(accCalibrate(), DELAY_ACC_CALIB_MS),
            CommandStep(save(), DELAY_AFTER_SAVE_MS),
        )
}
