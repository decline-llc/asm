from ..pipeline import StageResult


def run(ctx):
    values = {"roots": sorted(ctx.scope.roots), "ip_cidrs": [str(n) for n in ctx.scope.networks],
              "exclude_saas": sorted(ctx.scope.excluded), "authorization": ctx.scope.authorized}
    ctx.write("scope.json", values)
    ctx.db.fact("scope", values)
    return StageResult(count=len(ctx.scope.roots) + len(ctx.scope.networks),
                       notes=["Only YAML-approved scope is used; discovered companies/domains do not expand it"])
