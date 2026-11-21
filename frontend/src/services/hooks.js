import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

let metaCache = null

export function useMeta() {
  const [meta, setMeta] = useState(metaCache)
  useEffect(() => {
    if (metaCache) return
    api.meta().then((m) => {
      metaCache = m
      setMeta(m)
    }).catch(() => {})
  }, [])
  return meta
}

/** Carrega um recurso e, opcionalmente, atualiza a cada `interval` ms (placar "quase em tempo real"). */
export function usePolled(loader, deps, interval = 0) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const reload = useCallback(async () => {
    try {
      const d = await loaderRef.current()
      setData(d)
      setError(null)
      return d
    } catch (e) {
      setError(e)
      return null
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    setLoading(true)
    reload()
    if (!interval) return undefined
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') reload()
    }, interval)
    return () => clearInterval(id)
  }, [reload, interval])

  return { data, error, loading, reload, setData }
}
