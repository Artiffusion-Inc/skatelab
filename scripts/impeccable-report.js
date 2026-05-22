// scripts/impeccable-report.js
let input = '';
process.stdin.setEncoding('utf-8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  let findings;
  try {
    findings = JSON.parse(input);
  } catch {
    // impeccable may output non-JSON before the JSON
    const jsonMatch = input.match(/\[[\s\S]*\]/);
    if (jsonMatch) findings = JSON.parse(jsonMatch[0]);
    else { console.log('No findings'); process.exit(0); }
  }

  if (!Array.isArray(findings)) { console.log('No findings'); process.exit(0); }

  const errors = findings.filter(f => f.severity === 'error');
  const warnings = findings.filter(f => f.severity === 'warning');

  if (warnings.length > 0) {
    console.log(`\nWarnings (${warnings.length}):`);
    for (const w of warnings) {
      console.log(`  ⚠ ${w.rule || w.id}: ${w.message} (${w.file}:${w.line || '?'})`);
    }
  }

  if (errors.length > 0) {
    console.error(`\nErrors (${errors.length}):`);
    for (const e of errors) {
      console.error(`  ✗ ${e.rule || e.id}: ${e.message} (${e.file}:${e.line || '?'})`);
    }
    console.error(`\n${errors.length} error(s) found`);
    process.exit(1);
  }

  console.log(`\n${findings.length} finding(s): ${errors.length} errors, ${warnings.length} warnings`);
  process.exit(0);
});