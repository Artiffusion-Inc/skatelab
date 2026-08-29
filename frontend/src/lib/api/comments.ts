import { useMutation, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { apiPost } from "@/lib/api-client"

export const CommentResponseSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  coach_id: z.string(),
  content: z.string(),
  created_at: z.string(),
})

export type CommentResponse = z.infer<typeof CommentResponseSchema>
export type CreateCommentInput = { sessionId: string; content: string }

export function useCreateComment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, content }: CreateCommentInput) =>
      apiPost(`/sessions/${sessionId}/comments`, CommentResponseSchema, { content }),
    onSuccess: (_comment, { sessionId }) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
    },
  })
}
