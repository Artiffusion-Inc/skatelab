package ru.skatelab.shared.models

val elementLabelsRu: Map<String, String> = mapOf(
    "waltz_jump" to "Вальсовый прыжок",
    "toe_loop" to "Тулуп",
    "flip" to "Флип",
    "lutz" to "Лютц",
    "salchow" to "Сальхов",
    "loop" to "Луп",
    "axel" to "Аксель",
    "three_turn" to "Тройной",
    "spin" to "Вращение",
)

fun String.elementLabelRu(): String = elementLabelsRu[this] ?: this.replaceFirstChar { it.uppercase() }
