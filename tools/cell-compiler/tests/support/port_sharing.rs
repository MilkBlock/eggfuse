pub const SOURCE: &str = r#"
(datatype E (N i64) (F E) (G E))
(ruleset a) (ruleset b) (ruleset c)
(rule ((= x (N 0)) (= y (N 1)) (= z (N 2)))
      ((F x) (F y) (F z) (union x y)) :ruleset a)
(rule ((= x (N 0)) (= y (N 1)) (= z (N 2)))
      ((F x) (F y) (F z) (union y z)) :ruleset b)
(rule ((= f (F x))) ((G f)) :ruleset c)
(N 0) (N 1) (N 2)
(run-schedule (seq (run a) (run b) (run c)))
(check (= (G (F (N 0))) (G (F (N 2)))))
"#;
