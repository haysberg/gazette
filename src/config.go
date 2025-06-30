package main

import (
	"log"

	"github.com/BurntSushi/toml"
)

func setupFeeds() {
	var feedlist FeedList
	if _, err := toml.DecodeFile("config.toml", &feedlist); err != nil {
		log.Fatalf("Error loading config.toml: %v", err)
	}
	for _, feed := range feedlist.Feeds {
		db.Create(&feed)
	}
}
