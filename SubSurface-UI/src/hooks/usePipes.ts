import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPipes } from "../api/pipes";
import type { FilterState, Pipe, RiskLevel } from "../types/pipe";
import { CRITICAL_TABLE_LIMIT, RISK_LEVELS } from "../constants/colors";

const DEFAULT_RISK: RiskLevel[] = ["Critical", "High", "Medium", "Low"];

export function usePipes() {
  const [pipes, setPipes] = useState<Pipe[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchPipes(true);
        if (cancelled) return;
        setPipes(data.records);
        setSource(data.source);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load pipe data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const materials = useMemo(
    () => [...new Set(pipes.map((p) => p.material))].sort(),
    [pipes],
  );

  const wards = useMemo(
    () => [...new Set(pipes.map((p) => p.ward))].sort(),
    [pipes],
  );

  const pipeTypes = useMemo(
    () => [...new Set(pipes.map((p) => p.pipe_type))].sort(),
    [pipes],
  );

  const [filters, setFilters] = useState<FilterState>({
    riskLevels: DEFAULT_RISK,
    materials: [],
    wards: [],
    pipeTypes: [],
    minRiskScore: 0,
    colorMode: "risk",
  });

  useEffect(() => {
    if (!pipes.length) return;
    setFilters((prev) => ({
      ...prev,
      materials: prev.materials.length ? prev.materials : materials,
      wards: prev.wards.length ? prev.wards : wards,
      pipeTypes: prev.pipeTypes.length ? prev.pipeTypes : pipeTypes,
    }));
  }, [pipes, materials, wards, pipeTypes]);

  const updateFilters = useCallback((patch: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  }, []);

  const filteredPipes = useMemo(() => {
    return pipes.filter((pipe) => {
      if (!filters.riskLevels.includes(pipe.risk_level)) return false;
      if (!filters.materials.includes(pipe.material)) return false;
      if (!filters.wards.includes(pipe.ward)) return false;
      if (!filters.pipeTypes.includes(pipe.pipe_type)) return false;
      if (pipe.risk_score < filters.minRiskScore) return false;
      return true;
    });
  }, [pipes, filters]);

  const criticalTableRows = useMemo(() => {
    return filteredPipes
      .filter((p) => p.risk_level === "Critical")
      .sort((a, b) => b.risk_percentile - a.risk_percentile)
      .slice(0, CRITICAL_TABLE_LIMIT);
  }, [filteredPipes]);

  const stats = useMemo(() => {
    const critical = filteredPipes.filter((p) => p.risk_level === "Critical").length;
    const high = filteredPipes.filter((p) => p.risk_level === "High").length;
    const avgRisk =
      filteredPipes.length > 0
        ? filteredPipes.reduce((sum, p) => sum + p.risk_score, 0) / filteredPipes.length
        : 0;

    return {
      total: filteredPipes.length,
      critical,
      high,
      avgRisk,
      networkTotal: pipes.length,
      networkCritical: pipes.filter((p) => p.risk_level === "Critical").length,
    };
  }, [filteredPipes, pipes]);

  const resetFilters = useCallback(() => {
    setFilters({
      riskLevels: DEFAULT_RISK,
      materials,
      wards,
      pipeTypes,
      minRiskScore: 0,
      colorMode: "risk",
    });
  }, [materials, wards, pipeTypes]);

  const showCriticalOnly = useCallback(() => {
    setFilters((prev) => ({
      ...prev,
      riskLevels: ["Critical"],
      minRiskScore: 0,
    }));
  }, []);

  return {
    pipes,
    source,
    loading,
    error,
    filters,
    updateFilters,
    resetFilters,
    showCriticalOnly,
    filteredPipes,
    criticalTableRows,
    stats,
    materials,
    wards,
    pipeTypes,
    riskLevels: RISK_LEVELS,
  };
}
