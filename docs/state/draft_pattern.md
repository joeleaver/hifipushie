# STATE: draft_pattern (garment step 4, T5) -> codified.md C285
Tool draft_pattern(name, garment, design, declarations, options, sa): the agent's own FreeSewing design (Node, no network,
fs read-only, 60 s; errors name design.mjs's line) + declarations in step 1's names -> draft_own.block (the one
converter, a cloth.pieces block) -> cloth.mesh (all PATTERN_KEYS) -> general flat gate -> step 4 + flat sheet.
pattern_check and chain_garment's gate read an own draft's step 4. garment_record.READS: step 4 reads 1 and 3.
Proof (HOME /mnt/data/hifipushie/t5, model wf_simon; designs in /mnt/data/hifipushie/t5/designs, first versions in
examples/draft_own/): shirt on brian PASS; hussar body on bent PASS. After judging beside the reference the hussar's
cutaway was redrafted (CF shorter, tip out, hip length; PASS) and the shirt cuff widened (wrist + 80): those newer
designs are only in /mnt/data/hifipushie/t5/designs (copy them to examples/draft_own/).
chain_garment on the shirt: refused "cuff.L closed 166 mm does not clear the limb". After the redraft the chain job
answered from its cache: the spec holds only {from, dir}, so a redraft into the same dir has the same job key.
Unverified: chain build past the cuff; placement (wrap) of own pieces; collar_band/collar names vs chain roles (T8);
the slow test tier.
NEXT: put a digest of draft.json + declarations.json in the spec's pattern {"from": "own", "dir", "digest"}
(draft_own_tool.run; cloth.validate allows "digest"), redraft the shirt, rerun chain_garment to its structure answer.
