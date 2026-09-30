import { useState } from 'react'
export function useDisclosure(initial = false) { const [isOpen, setIsOpen] = useState(initial); return { isOpen, open: () => setIsOpen(true), close: () => setIsOpen(false), toggle: () => setIsOpen((value) => !value) } }
