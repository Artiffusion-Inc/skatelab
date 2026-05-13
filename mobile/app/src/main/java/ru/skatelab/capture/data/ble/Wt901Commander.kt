package ru.skatelab.capture.data.ble

/**
 * Builds WT901 BLE command packets and sequences.
 *
 * All commands are 5 bytes: [0xFF, 0xAA, b3, b4, b5].
 * Byte 3 = register address for writes, 0x27 for register reads.
 *
 * Unlock must be sent before EVERY configuration write — the 10-second
 * window expires after Save. Register reads do NOT need Unlock.
 */
object Wt901Commander {

    // Register addresses
    private const val REG_OUTPUT_CONTENT: Byte = 0x02
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

    // --- Individual command builders ---

    /** Unlock the sensor for configuration (opens 10-second window). */
    fun unlock(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x69, 0x88.toByte(), 0xB5.toByte())

    /** Start accelerometer hardware calibration — sensor must be still and level. */
    fun accCalibrate(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, CMD_ACC_CALIB, 0x01, 0x00)

    /** Stop active calibration (ACC or MAG). */
    fun stopCalibration(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, CMD_ACC_CALIB, 0x00, 0x00)

    /**
     * Set OutputContent register (0x02).
     * @param value Bitmask of output types to enable (XAMLCORP SDK flags).
     *   Time=0x0001, ACC=0x0002, GYRO=0x0004, Angle=0x0008,
     *   Magnetic=0x0010, Quaternion=0x0040
     *   0x0046 = ACC + GYRO + Quaternion
     *   0x0000 = disable all output
     */
    fun setOutputContent(value: Int): ByteArray =
        byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, REG_OUTPUT_CONTENT, value.toByte(), (value shr 8).toByte())

    /**
     * Set OutputRate register (0x03).
     * @param value Rate code. 0x09 = 100Hz.
     */
    fun setOutputRate(value: Int): ByteArray =
        byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, REG_OUTPUT_RATE, value.toByte(), 0x00)

    /** Factory reset — restores all registers to defaults. */
    fun factoryReset(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x00, 0xFF.toByte(), 0x00)

    /** Save configuration to EEPROM (causes output mode switch). */
    fun save(): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x00, 0x00, 0x00)

    /**
     * Read a register value (query-response via 0x71 notification).
     * Register reads do NOT need Unlock.
     */
    fun readRegister(reg: Int): ByteArray =
        byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, REG_READ_OPCODE, reg.toByte(), 0x00)

    // --- Command sequences ---

    /**
     * Full configuration sequence:
     * 1. Unlock → OutputContent(0x0046) → OutputRate(100Hz) → Save
     * 2. Unlock → ACC Calibrate → wait 2s → Save
     * Run once after initial connection. Sensor must be still during step 2.
     *
     * WARNING: accCalibrate() can corrupt ACC offset on some sensors.
     * Use configureSequenceNoAccCal() for sensors with ACC issues.
     */
    fun configureSequence(): List<CommandStep> = listOf(
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setOutputContent(0x0046), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(setOutputRate(0x09), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(accCalibrate(), DELAY_ACC_CALIB_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )

    /**
     * Configuration without ACC calibration.
     * Use for sensors where accCalibrate() corrupted the ACC offset.
     */
    fun configureSequenceNoAccCal(): List<CommandStep> = listOf(
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setOutputContent(0x0046), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(setOutputRate(0x09), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )

    /**
     * Factory reset then reconfigure without ACC calibration.
     * Use to recover a sensor with corrupted ACC offset.
     */
    fun factoryResetSequence(): List<CommandStep> = listOf(
        CommandStep(stopCalibration(), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(factoryReset(), 2000L),
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setOutputContent(0x0046), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(setOutputRate(0x09), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )

    /**
     * Start streaming: Unlock → OutputContent 0x0046 → Save.
     * Sends at recording start. ~750ms total.
     */
    fun startStreamingSequence(): List<CommandStep> = listOf(
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setOutputContent(0x0046), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )

    /**
     * Stop streaming: Unlock → OutputContent 0x0000 → Save.
     * Sends at recording end. ~750ms total.
     */
    fun stopStreamingSequence(): List<CommandStep> = listOf(
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setOutputContent(0x0000), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )
}
