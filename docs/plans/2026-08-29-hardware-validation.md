# Hardware validation runbook

## Capture

1. Подключить LEFT и RIGHT WT901.
2. Записать 10–15 секунд с одной попыткой Axel.
3. Сохранить из capture directory:
   - `*.mp4`;
   - `*_left.binpb`;
   - `*_right.binpb`;
   - `manifest.json`.

## Local smoke check

```bash
cd ml
python scripts/inspect_imu.py /path/to/*_left.binpb --t0-ns <manifest.t0_ns>
python scripts/inspect_imu.py /path/to/*_right.binpb --t0-ns <manifest.t0_ns>
```

Проверить:

- оба файла имеют samples > 0;
- `gaps` совпадает с ожидаемыми reconnects;
- фактическая частота близка к `imu_rate_hz`;
- timestamps монотонны;
- peak offset попадает внутрь длительности видео.

## Acceptance criteria для первой серии

- минимум 10 валидных попыток;
- `imu_offset_error <= 40 ms` в 90% попыток;
- `imu_rate_error <= 5 Hz` в 90% попыток;
- `sensor_confidence >= 0.6` в 90% попыток;
- `rotation_symmetry` и `landing_stability` сравниваются с ручной оценкой тренера;
- ни одна повреждённая запись не проходит decoder молча.

## Решение после серии

- Если transport criteria не выполнены — исправлять Android/BLE timebase.
- Если transport criteria выполнены, но fused metrics не коррелируют с оценкой
  тренера — менять признаки/окно, а не железо.
- Только после этого обучать element-specific model и расширять список элементов.
