package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.SkillProgressResponse
import ru.skatelab.shared.models.UserLevelResponse
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class GamificationStateTest {
    @Test
    fun loaded_preservesLevelAndSkills() {
        val level = UserLevelResponse(
            id = "level-1",
            userId = "user-1",
            level = 3,
            totalXp = 340,
            xpToNext = 700,
            title = "Спортсмен",
            createdAt = "2026-07-04T12:00:00Z",
            updatedAt = "2026-07-04T12:00:00Z",
        )
        val skill = SkillProgressResponse(
            id = "progress-1",
            userId = "user-1",
            skillId = "jumps_bronze",
            category = "jumps",
            tier = "bronze",
            unlocked = true,
            unlockedAt = "2026-07-04T12:00:00Z",
            consecutiveSessions = 4,
            bestScore = 8.5,
            xpReward = 50,
        )

        val state: GamificationUiState = GamificationUiState.Loaded(level, listOf(skill))

        val loaded = assertIs<GamificationUiState.Loaded>(state)
        assertEquals(level, loaded.level)
        assertEquals(listOf(skill), loaded.skills)
    }

    @Test
    fun error_carriesTypedAppError() {
        val state: GamificationUiState = GamificationUiState.Error(AppError.Server())

        val error = assertIs<GamificationUiState.Error>(state)
        assertIs<AppError.Server>(error.error)
    }
}
