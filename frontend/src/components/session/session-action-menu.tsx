"use client"

import { MoreVertical, Share2, GitCompare, Printer, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import Link from "next/link"
import { useTranslations } from "@/i18n"

interface SessionActionMenuProps {
  sessionId: string
  onDelete: () => void
  onShare: () => void
}

export function SessionActionMenu({ sessionId, onDelete, onShare }: SessionActionMenuProps) {
  const t = useTranslations("session")
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("actions")}>
          <MoreVertical className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onShare}>
          <Share2 className="mr-2 h-4 w-4" /> {t("share")}
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href={`/compare?left=${sessionId}`}>
            <GitCompare className="mr-2 h-4 w-4" /> {t("compare")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => window.print()}>
          <Printer className="mr-2 h-4 w-4" /> {t("printReport")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
          <Trash2 className="mr-2 h-4 w-4" /> {t("delete")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
