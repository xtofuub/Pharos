INSERT INTO users (email, username, password_hash, created_at) VALUES ('fake.user@gmail.com', 'jsmith', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', '2024-01-15 10:30:00');
INSERT INTO users (email, username, password_hash, created_at) VALUES ('fake.user@yahoo.com', 'yahoo_user', 'a94a8fe5ccb19ba61c4c0873d391e987982fbbd3', '2024-02-20 14:45:00');
INSERT INTO users (email, username, password_hash, created_at) VALUES ('fake.user@outlook.com', 'outlook_user', '5f4dcc3b5aa765d61d8327deb882cf99', '2024-03-10 09:15:00');
INSERT INTO users (email, username, password_hash, created_at) VALUES ('fake.user@protonmail.com', 'proton_user', '098f6bcd4621d373cade4e832627b4f6', '2024-04-05 16:20:00');
INSERT INTO users (email, username, password_hash, created_at) VALUES ('fake.user@github.com', 'devuser_42', '5ebe2294ecd0e0f08eab7690d2a6ee69', '2024-05-12 11:50:00');
INSERT INTO accounts (user_id, service, account_id, last_login) VALUES (1, 'Google', 'fake.user@gmail.com', '2024-06-01 08:00:00');
INSERT INTO accounts (user_id, service, account_id, last_login) VALUES (2, 'Yahoo', 'fake.user@yahoo.com', '2024-06-02 09:30:00');
INSERT INTO accounts (user_id, service, account_id, last_login) VALUES (3, 'Microsoft', 'fake.user@outlook.com', '2024-06-03 14:15:00');
