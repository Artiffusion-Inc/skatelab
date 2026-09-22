export const H36M_SKELETON_CONNECTIONS = [
  // Torso and head
  [0, 7],
  [7, 8],
  [8, 9],
  [9, 10],
  // Right leg
  [0, 1],
  [1, 2],
  [2, 3],
  // Left leg
  [0, 4],
  [4, 5],
  [5, 6],
  // Right arm: thorax -> shoulder -> elbow -> wrist
  [8, 14],
  [14, 15],
  [15, 16],
  // Left arm: thorax -> shoulder -> elbow -> wrist
  [8, 11],
  [11, 12],
  [12, 13],
] as const
