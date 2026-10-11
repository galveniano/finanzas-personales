import { useRef, useState } from 'react'
import type { DragEvent } from 'react'

/** `input` es el <input type="file"> oculto (ponlo en el árbol), `elegir()` abre el selector, `zona` son las props del
 *  contenedor que admite arrastrar y `arrastrando` sirve para resaltarlo. `filtro` descarta los ficheros que no valen. */
export function useSubida({ accept, multiple, filtro, onFicheros }: {
  accept: string; multiple?: boolean; filtro?: (f: File) => boolean; onFicheros: (ficheros: File[]) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  const [arrastrando, setArrastrando] = useState(false)
  const recibir = (lista: FileList | null) => {
    const validos = [...(lista ?? [])].filter((f) => !filtro || filtro(f))
    if (validos.length) onFicheros(validos)
  }
  const input = <input ref={ref} type="file" accept={accept} multiple={multiple} hidden onChange={(e) => { recibir(e.target.files); e.target.value = '' }} />
  const zona = {
    onDragOver: (e: DragEvent<HTMLElement>) => { e.preventDefault(); setArrastrando(true) },
    // Al pasar sobre un hijo también salta dragleave: solo cuenta si sale de verdad del contenedor
    onDragLeave: (e: DragEvent<HTMLElement>) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setArrastrando(false) },
    onDrop: (e: DragEvent<HTMLElement>) => { e.preventDefault(); setArrastrando(false); recibir(e.dataTransfer.files) },
  }
  return { input, elegir: () => ref.current?.click(), zona, arrastrando }
}
