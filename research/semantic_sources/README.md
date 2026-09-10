# Future semantic source adapters

現在のPipelineはPR #26で生成済みの125,000件Review Queueを`jmdict/source-lock.json`でWorkflow Run、Artifact、Path、件数、SHA-256まで固定して取得します。QueueにはJMdict意味候補付き120,000件とContext候補5,000件が含まれ、両方を同じ共通Schema・同じReview Queueで非AI・決定論的に処理します。日次更新されるJMdictの可変URLを再取得して、既存候補を入れ替えることはしません。

JMdict意味候補はSource所有データとして保持し、Decision Ledgerから上書きしません。Reviewでは不足している極性・強度・文脈・Task候補・外部Action Riskだけを追加します。将来、別の外部Source Adapterを追加する場合もURL・Version・SHA-256・Licenseを固定し、出力を同じReview Queueへ送ります。Candidate抽出だけで承認またはRuntime昇格することは禁止します。
